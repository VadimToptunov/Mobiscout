// A device-free WebdriverIO runtime for executing a generated WebdriverIO kit.
//
// Installs the fake app (wdio_fake_app.mjs) plus Mocha's describe/it, loads the kit's own
// wdio.conf.js (so its beforeTest hook — the app restart — runs before every test), imports
// every spec and runs the tests in order. Prints PASS/FAIL per test; exits 1 on any failure.
//
// usage: MOBISCOUT_FAKE_APP=app.json node wdio_fake_runner.mjs <kit-dir>

import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { installFakeApp } from './wdio_fake_app.mjs';

const kit = process.argv[2];
installFakeApp();

const tests = [];
let suite = '';
globalThis.describe = (title, body) => {
    const outer = suite;
    suite = outer ? `${outer} ${title}` : title;
    body();
    suite = outer;
};
globalThis.it = (title, fn) => tests.push({ title: `${suite} > ${title}`, fn });

const { config } = await import(pathToFileURL(join(kit, 'wdio.conf.js')).href);
const specsDir = join(kit, 'test', 'specs');
for (const file of readdirSync(specsDir).filter((f) => f.endsWith('.e2e.js')).sort()) {
    await import(pathToFileURL(join(specsDir, file)).href);
}

let failed = 0;
for (const test of tests) {
    try {
        if (config.beforeTest) await config.beforeTest();
        await test.fn();
        console.log(`PASS: ${test.title}`);
    } catch (error) {
        failed += 1;
        console.log(`FAIL: ${test.title}: ${error.message}`);
    }
}
console.log(`${tests.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : tests.length ? 0 : 2);
