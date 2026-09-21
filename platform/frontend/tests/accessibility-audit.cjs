/** Automated accessibility checks and accessibility-tree evidence.
 * This complements, but does not replace, a human screen-reader audit.
 */
const { chromium } = require('playwright');
const axe = require('axe-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const base = process.env.PLATFORM_URL || 'http://127.0.0.1:8772';
const outputDir = path.join(__dirname, 'artifacts/accessibility');
fs.mkdirSync(outputDir, { recursive: true });

const audits = [];
let browser;

function summarizeTree(nodes) {
  const usefulRoles = new Set([
    'main', 'navigation', 'heading', 'button', 'link', 'textbox', 'combobox',
    'checkbox', 'alert', 'status', 'table', 'region', 'DisclosureTriangle',
  ]);
  return nodes
    .filter(node => usefulRoles.has(node.role?.value) && !node.ignored)
    .map(node => ({
      role: node.role?.value,
      name: node.name?.value || '',
      level: node.level?.value,
      disabled: node.disabled?.value,
      expanded: node.expanded?.value,
      checked: node.checked?.value,
    }));
}

async function audit(page, name) {
  await page.addScriptTag({ content: axe.source });
  const result = await page.evaluate(async () => axe.run(document, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] },
    resultTypes: ['violations', 'incomplete', 'passes'],
  }));
  const session = await page.context().newCDPSession(page);
  await session.send('Accessibility.enable');
  const tree = await session.send('Accessibility.getFullAXTree');
  const entry = {
    name,
    url: page.url(),
    violations: result.violations.map(item => ({
      id: item.id,
      impact: item.impact,
      help: item.help,
      helpUrl: item.helpUrl,
      nodes: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })),
    })),
    incomplete: result.incomplete.map(item => ({
      id: item.id,
      impact: item.impact,
      help: item.help,
      helpUrl: item.helpUrl,
      targets: item.nodes.map(node => node.target),
    })),
    passCount: result.passes.length,
    accessibilityTree: summarizeTree(tree.nodes),
  };
  audits.push(entry);
  return entry;
}

(async () => {
  browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const page = await context.newPage();

  await page.goto(base);
  await page.getByRole('heading', { name: 'Create a dataset' }).waitFor();
  await audit(page, 'Start screen');

  await page.getByRole('button', { name: 'Create your own dataset', exact: true }).click();
  await page.getByRole('heading', { name: 'Review your dataset' }).waitFor();
  await page.getByRole('button', { name: 'Edit tables, columns and relationships' }).click();
  await audit(page, 'Guided editor');

  await page.getByRole('button', { name: 'Advanced JSON' }).click();
  await page.locator('textarea.json-editor').fill('{broken');
  await page.getByRole('button', { name: 'Apply and validate changes' }).click();
  await page.getByRole('alert').waitFor();
  await audit(page, 'Recoverable JSON error');

  await page.getByRole('button', { name: 'Discard edits' }).click();
  await page.getByRole('button', { name: 'Guided editor' }).click();
  await page.getByRole('button', { name: 'Apply and validate changes' }).click();
  await page.getByRole('button', { name: 'Generate dataset' }).click();
  await page.getByRole('heading', { name: 'Evidence report' }).waitFor({ timeout: 60000 });
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Evidence report');
  await audit(page, 'Single-table evidence report');

  await page.getByRole('button', { name: 'Start another dataset' }).click();
  await page.locator('[data-example="retail_relational"]').click();
  await page.getByRole('button', { name: 'Edit tables, columns and relationships' }).click();
  await audit(page, 'Relational guided editor');
  await page.getByRole('button', { name: 'Hide dataset editor' }).click();
  await page.getByRole('button', { name: 'Generate dataset' }).click();
  await page.getByRole('heading', { name: 'Evidence report' }).waitFor({ timeout: 60000 });
  await page.getByRole('button', { name: /order_lines \(/ }).click();
  assert.equal(await page.getByRole('status').filter({ hasText: 'Showing result table order_lines' }).count(), 1);
  await page.locator('summary').filter({ hasText: /unconfirmed assumptions/ }).click();
  await audit(page, 'Relational evidence report with details expanded');

  await page.getByRole('button', { name: 'Start another dataset' }).click();
  const rows = ['timestamp,value'];
  for (let index = 0; index < 120; index += 1) {
    rows.push(`${new Date(Date.UTC(2026, 0, 1, index)).toISOString()},${(index * 37) % 101}`);
  }
  await page.locator('input[type="file"][accept=".csv,.tsv,.txt"]').setInputFiles({
    name: 'public_fixture.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(rows.join('\n')),
  });
  await page.getByRole('heading', { name: 'Review your dataset' }).waitFor();
  await page.getByRole('button', { name: 'Apply suggested fix' }).waitFor();
  await audit(page, 'Uploaded-data review with suggested fix');

  const violations = audits.flatMap(entry => entry.violations.map(violation => ({ screen: entry.name, ...violation })));
  const report = {
    generatedUtc: new Date().toISOString(),
    tool: `axe-core ${axe.version} and Chrome accessibility tree`,
    scope: audits.map(entry => entry.name),
    summary: {
      screens: audits.length,
      violations: violations.length,
      incompleteChecksRequiringReview: audits.reduce((sum, entry) => sum + entry.incomplete.length, 0),
    },
    limitations: [
      'Automated rules and an accessibility tree cannot judge announcement quality or task comprehension.',
      'A human must complete the companion Orca protocol before claiming a completed screen-reader audit.',
      'No claim of WCAG conformance is made.',
    ],
    audits,
  };
  fs.writeFileSync(path.join(outputDir, 'automated-audit.json'), JSON.stringify(report, null, 2));
  assert.deepEqual(violations, [], `Accessibility violations found: ${JSON.stringify(violations, null, 2)}`);
  console.log(JSON.stringify(report.summary));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(async () => {
  await browser?.close();
});
