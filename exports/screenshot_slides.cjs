// Screenshot every slide as a JPG using Edge (headless).
// Run: node exports/screenshot_slides.js
// Output: exports/slide_01.jpg … slide_10.jpg

const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const DECK = 'file:///' + path.resolve(__dirname, '..', 'html', 'midterm_deck.html').replace(/\\/g, '/');
const OUT  = __dirname;
const TOTAL = 10;

(async () => {
    const browser = await puppeteer.launch({
        executablePath: EDGE,
        headless: true,
        args: ['--no-sandbox', '--disable-web-security', '--allow-file-access-from-files'],
    });

    const page = await browser.newPage();
    await page.setViewport({ width: 1920, height: 1080 });
    await page.goto(DECK, { waitUntil: 'networkidle0', timeout: 15000 });

    for (let n = 1; n <= TOTAL; n++) {
        await page.evaluate((n) => { if (typeof showSpread === 'function') showSpread(n); }, n);
        await new Promise(r => setTimeout(r, 600)); // let any transitions settle
        const file = path.join(OUT, `slide_${String(n).padStart(2, '0')}.jpg`);
        await page.screenshot({ path: file, type: 'jpeg', quality: 95 });
        console.log(`  saved ${path.basename(file)}`);
    }

    await browser.close();
    console.log('Done.');
})();
