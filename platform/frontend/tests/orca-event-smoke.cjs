/** Exercise key app states in a headful Chrome window while Orca is running.
 * This verifies the AT-SPI event path. It is not a human screen-reader audit.
 */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const base = process.env.PLATFORM_URL || 'http://127.0.0.1:8772';
const output = path.join(__dirname, 'artifacts/accessibility/orca-event-smoke.json');
const states = [];
let browser;

(async () => {
  browser = await chromium.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: false,
    args: ['--force-renderer-accessibility'],
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(base);
  await page.getByRole('heading', { name: 'Create a dataset' }).waitFor();
  await page.getByRole('link', { name: 'Skip to main content' }).focus();
  await page.waitForTimeout(500);
  states.push('start and skip link focused');

  const create = page.getByRole('button', { name: 'Create your own dataset', exact: true });
  await create.focus();
  await page.waitForTimeout(500);
  await page.keyboard.press('Enter');
  await page.getByRole('heading', { name: 'Review your dataset' }).waitFor();
  await page.waitForTimeout(800);
  states.push('design screen entered with keyboard');

  const editor = page.getByRole('button', { name: 'Edit tables, columns and relationships' });
  await editor.focus();
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Advanced JSON' }).focus();
  await page.waitForTimeout(500);
  await page.keyboard.press('Enter');
  const json = page.locator('textarea.json-editor');
  await json.focus();
  await json.fill('{broken');
  await page.getByRole('button', { name: 'Apply and validate changes' }).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('alert').waitFor();
  await page.getByRole('alert').focus();
  await page.waitForTimeout(1000);
  states.push('recoverable JSON error exposed as alert');

  await page.getByRole('button', { name: 'Discard edits' }).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Guided editor' }).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Apply and validate changes' }).focus();
  await page.keyboard.press('Enter');
  const generate = page.getByRole('button', { name: 'Generate dataset' });
  await generate.focus();
  await page.waitForTimeout(500);
  await page.keyboard.press('Enter');
  await page.getByRole('heading', { name: 'Evidence report' }).waitFor({ timeout: 60000 });
  await page.waitForTimeout(1000);
  await page.getByRole('link', { name: 'Download CSV' }).focus();
  await page.waitForTimeout(800);
  states.push('evidence report and download link focused');

  fs.writeFileSync(output, JSON.stringify({
    generatedUtc: new Date().toISOString(),
    result: 'AT-SPI event-path exercise completed',
    states,
    limitation: 'Programmatic focus and Orca debug events do not establish intelligibility to a human screen-reader user.',
  }, null, 2));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(async () => {
  await browser?.close();
});
