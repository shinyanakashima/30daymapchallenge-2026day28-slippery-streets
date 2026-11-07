// Load the built site, fail on console errors / failed requests, and save a screenshot.
// usage: node scripts/check_site.cjs [url] [out.png]
const { chromium } = require('playwright');

(async () => {

const url = process.argv[2] || 'http://localhost:8000/';
const out = process.argv[3] || 'docs/screenshot.png';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 900 }, deviceScaleFactor: 1 });
const problems = [];
page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`); });
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
page.on('response', (r) => { if (r.status() >= 400) problems.push(`${r.status()} ${r.url()}`); });
page.on('requestfailed', (r) => problems.push(`failed: ${r.url()} ${r.failure()?.errorText}`));

await page.goto(url, { waitUntil: 'networkidle' });
await page.waitForFunction(() => document.getElementById('bigNumber').textContent.includes('%'));
await page.waitForTimeout(1500);
await page.screenshot({ path: out });
console.log('big number:', await page.textContent('#bigNumber'));

// mobile layout + language switch
const m = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
m.on('console', (x) => { if (x.type() === 'error') problems.push(`mobile console: ${x.text()}`); });
m.on('response', (r) => { if (r.status() >= 400) problems.push(`mobile ${r.status()} ${r.url()}`); });
await m.goto(url, { waitUntil: 'networkidle' });
await m.click('[data-lang="ja"]');
await m.waitForTimeout(1200);
await m.screenshot({ path: out.replace(/\.png$/, '-mobile.png') });

await browser.close();
if (problems.length) { console.error(problems.join('\n')); process.exit(1); }
console.log('ok: no console errors, no 4xx/5xx');
})();
