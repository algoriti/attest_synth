/** Browser regression for proposal -> review -> generation -> visible CSV download. */
const { chromium } = require(process.argv[2]);
const fs = require('node:fs');
const path = require('node:path');

const artifacts = path.join(__dirname, 'artifacts', 'assistant-workflow');
fs.mkdirSync(artifacts, { recursive: true });

(async () => {
  const result = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../../backend/benchmarks/results/assistant_employee_behavioral_check.json')));
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.route('**/api/assistant', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        spec: result.spec,
        notice: 'Proposal only. Review its rules and assumptions before generating.',
        review: result.proposal_review,
      }),
    });
  });
  const base = process.env.PLATFORM_URL || 'http://127.0.0.1:8770';
  await page.goto(base);
  await page.getByLabel('Your scenario').fill('Create 500 employees with linked attendance, projects, assignments, tasks and reports.');
  await page.getByRole('button', { name: 'Propose a dataset', exact: true }).click();
  await page.getByRole('heading', { name: 'Review your dataset', exact: true }).waitFor();
  if (!await page.getByText('500 employees', { exact: true }).isVisible()) throw new Error('Explicit employee count was not shown.');
  await page.screenshot({ path: path.join(artifacts, 'proposal-review.png'), fullPage: true });

  await page.getByRole('button', { name: 'Generate dataset', exact: true }).click();
  await page.getByRole('heading', { name: 'Evidence report', exact: true }).waitFor({ timeout: 60000 });
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: /Download CSV/ }).first().click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  if (!downloadPath || fs.statSync(downloadPath).size === 0) throw new Error('CSV download was empty.');
  await page.getByText(/\.csv downloaded \([\d,]+ bytes\)\./).waitFor();
  await page.screenshot({ path: path.join(artifacts, 'evidence-and-download.png'), fullPage: true });
  if (errors.length) throw new Error(errors.join('\n'));
  const evidence = {
    proposal_tables: result.spec.tables.map(table => table.name),
    downloaded_file: download.suggestedFilename(),
    downloaded_bytes: fs.statSync(downloadPath).size,
    page_errors: errors,
  };
  fs.writeFileSync(path.join(artifacts, 'result.json'), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
