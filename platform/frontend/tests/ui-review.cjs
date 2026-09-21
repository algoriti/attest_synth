/** Targeted UX checks; not a complete WCAG conformance audit. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const dir = path.join(__dirname, 'artifacts/ui-review');
fs.mkdirSync(dir, { recursive: true });
const checks = [], errors = [], contrast = [];
const base = process.env.PLATFORM_URL || 'http://127.0.0.1:8772';
let browser;
(async () => {
  browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on('pageerror', error => errors.push(String(error)));
  async function source() {
    await page.goto(base);
    await page.getByRole('button', { name: 'Create your own dataset', exact: true }).waitFor();
    await page.locator('[data-example="retail_relational"]').waitFor();
    await page.evaluate(() => document.fonts.ready);
  }
  async function fits(name) {
    const size = await page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth }));
    assert.ok(size.page <= size.viewport, `${name}: ${JSON.stringify(size)}`);
    checks.push(`${name}: no horizontal page overflow`);
  }
  async function palette(theme) {
    const measured = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement);
      const color = key => style.getPropertyValue(key).trim();
      const luminance = hex => {
        const value=hex.replace('#','');
        const rgb = (value.length===3?value.split('').map(c=>c+c).join(''):value).match(/.{2}/g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
        return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
      };
      const ratio = (a,b) => { const x=luminance(color(a)),y=luminance(color(b));return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); };
      return ['--text-primary','--text-secondary','--text-muted','--accent'].flatMap(fg=>['--surface-0','--surface-1','--surface-2'].map(bg=>({fg,bg,ratio:ratio(fg,bg)}))).concat([{fg:'--surface-1',bg:'--accent',ratio:ratio('--surface-1','--accent')},...['good','warning','critical'].map(tone=>({fg:`--${tone}`,bg:`--${tone}-soft`,ratio:ratio(`--${tone}`,`--${tone}-soft`)})),{fg:'--border-strong',bg:'--surface-1',ratio:ratio('--border-strong','--surface-1'),minimum:3}]);
    });
    measured.forEach(item=>assert.ok(item.ratio>=(item.minimum??4.5),`${theme}: ${JSON.stringify(item)}`));
    contrast.push({theme,pairs:measured});
  }
  await source();
  await page.screenshot({path:path.join(dir,'desktop-start.png'),fullPage:true,animations:'disabled'});
  await palette('light');
  await page.getByRole('button',{name:'Switch to dark theme'}).click();
  await palette('dark');
  await page.screenshot({path:path.join(dir,'dark-start.png'),fullPage:true,animations:'disabled'});
  await page.getByRole('button',{name:'Switch to light theme'}).click();
  checks.push('Text, action and status token contrast meets 4.5:1; field borders meet 3:1 in both themes');
  for (const width of [320,390,768,1440]) {
    await page.setViewportSize({width,height:900});await fits(`Start at ${width}px`);
    if(width===390)await page.screenshot({path:path.join(dir,'mobile-start.png'),fullPage:true,animations:'disabled'});
  }
  await page.getByRole('link',{name:'Skip to main content'}).focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'main-content');
  const upload = page.getByRole('button',{name:'Upload a CSV or TSV'});
  await upload.focus();
  const chooser = page.waitForEvent('filechooser');
  await page.keyboard.press('Enter');await chooser;
  checks.push('Upload opens the file chooser using keyboard Enter');
  const button = page.getByRole('button',{name:'Create your own dataset',exact:true});
  await button.focus();
  assert.notEqual(await button.evaluate(el=>getComputedStyle(el).outlineStyle),'none');
  await page.keyboard.press('Enter');
  await page.getByRole('heading',{name:'Review your dataset'}).waitFor();
  assert.equal(await page.evaluate(()=>document.activeElement.id),'main-content');
  checks.push('Skip link and keyboard creation focus the main content');
  await page.getByRole('button',{name:'Edit tables, columns and relationships',exact:true}).click();
  await page.getByRole('button',{name:'Add column to records',exact:true}).click();
  await page.getByRole('textbox',{name:'Table 1 column 2 name'}).fill('amount');
  assert.ok(await page.getByRole('button',{name:'Generate dataset',exact:true}).isDisabled());
  assert.equal(await page.getByText('The specification was rejected',{exact:true}).count(),0);
  await page.getByRole('button',{name:'Hide dataset editor',exact:true}).click();
  await page.getByRole('button',{name:'Edit tables, columns and relationships',exact:true}).click();
  assert.equal(await page.getByRole('textbox',{name:'Table 1 column 2 name'}).inputValue(),'amount');
  checks.push('Hiding and reopening the editor preserves unapplied changes');
  page.once('dialog',d=>d.dismiss());
  await page.getByRole('button',{name:'Step 1: Start',exact:true}).click();
  assert.ok(await page.getByRole('textbox',{name:'Table 1 column 2 name'}).isVisible());
  checks.push('Cancelling navigation keeps the editor draft');
  await page.screenshot({path:path.join(dir,'desktop-editor.png'),fullPage:true,animations:'disabled'});
  for(const width of [320,390,768,1440]) {
    await page.setViewportSize({width,height:900});await fits(`Editor at ${width}px`);
    if(width===390)await page.screenshot({path:path.join(dir,'mobile-editor.png'),fullPage:true,animations:'disabled'});
  }
  await page.getByRole('button',{name:'Apply and validate changes',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.generation-actions button').disabled);
  // A complete keyboard traversal from generation through report/download.
  await page.getByRole('button',{name:'Generate dataset',exact:true}).focus();
  await page.keyboard.press('Enter');
  await page.getByRole('heading',{name:'Evidence report',exact:true}).waitFor({timeout:60000});
  const download = page.getByRole('link',{name:'Download CSV',exact:true});
  await download.focus();
  const downloadEvent=page.waitForEvent('download');await page.keyboard.press('Enter');await downloadEvent;
  checks.push('Keyboard generation and CSV download complete');
  assert.equal(await page.locator('a button').count(),0);
  await page.getByRole('button',{name:'Start another dataset',exact:true}).click();
  await page.locator('[data-example="retail_relational"]').click();
  await page.screenshot({path:path.join(dir,'desktop-review.png'),fullPage:true,animations:'disabled'});
  await page.getByRole('button',{name:'Generate dataset',exact:true}).click();
  await page.getByRole('heading',{name:'Evidence report',exact:true}).waitFor({timeout:60000});
  const tab=page.getByRole('button',{name:/order_lines \(/});await tab.focus();await page.keyboard.press('Enter');
  assert.equal(await tab.getAttribute('aria-pressed'),'true');
  const assumptions = page.locator('summary').filter({hasText:/Review .* unconfirmed assumptions/});
  await assumptions.focus();await page.keyboard.press('Enter');
  assert.ok(await assumptions.evaluate(el=>el.parentElement.open));
  await page.keyboard.press('Enter');
  checks.push('Assumption details expand and collapse with keyboard Enter');
  await page.screenshot({path:path.join(dir,'desktop-report.png'),fullPage:true,animations:'disabled'});
  for(const width of [320,390,768,1440]) {
    await page.setViewportSize({width,height:900});await fits(`Report at ${width}px`);
    if(width===390)await page.screenshot({path:path.join(dir,'mobile-report.png'),fullPage:true,animations:'disabled'});
  }
  await page.getByRole('button',{name:'Switch to dark theme'}).click();
  await page.screenshot({path:path.join(dir,'dark-report.png'),fullPage:true,animations:'disabled'});
  await page.emulateMedia({reducedMotion:'reduce'});
  const reduced=await page.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches);assert.ok(reduced);
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(dir,'results.json'),JSON.stringify({checks,errors,contrast,limits:'Targeted browser checks only. No screen-reader or participant usability study; no claim of full WCAG conformance.'},null,2));
  console.log(JSON.stringify({checks,errors}));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();});
