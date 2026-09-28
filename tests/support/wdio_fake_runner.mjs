// A device-free WebdriverIO runtime for executing a generated WebdriverIO kit.
//
// Installs the globals a WDIO spec relies on ($, driver, expect, describe, it), backed by a
// fake app model (screens of selector strings + transitions), loads the kit's own
// wdio.conf.js (so its beforeTest hook — the app restart — runs before every test), imports
// every spec and runs the tests in order. Prints PASS/FAIL per test; exits 1 on any failure.
//
// usage: MOBISCOUT_FAKE_APP=app.json node wdio_fake_runner.mjs <kit-dir>

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const kit = process.argv[2];
const model = JSON.parse(readFileSync(process.env.MOBISCOUT_FAKE_APP, 'utf8'));

const app = {
    screens: model.screens.map((s) => new Set(s)),
    transitions: new Map(model.transitions.map(([from, sel, to]) => [`${from}\u0000${sel}`, to])),
    start: model.start ?? 0,
    current: model.start ?? 0,
    typed: new Map(),
    present(sel) {
        return this.screens[this.current].has(sel);
    },
    validInput() {
        // A validating form: a submit only advances when what was typed is plausible.
        for (const [sel, text] of this.typed) {
            const s = sel.toLowerCase();
            if ((s.includes('email') || s.includes('mail')) && !text.includes('@')) return false;
            if (s.includes('password') && text.length < 4) return false;
        }
        return true;
    },
    tap(sel) {
        const next = this.transitions.get(`${this.current}\u0000${sel}`);
        if (next !== undefined && this.validInput()) {
            this.current = next;
            this.typed.clear();
        }
    },
    reset() {
        this.current = this.start;
        this.typed.clear();
    },
};

class FakeElement {
    constructor(selector) {
        this.selector = selector;
    }
    async isExisting() {
        return app.present(this.selector);
    }
    async isDisplayed() {
        return app.present(this.selector);
    }
    async isEnabled() {
        return true;
    }
    async getText() {
        return '';
    }
    async click() {
        if (!app.present(this.selector)) throw new Error(`click on missing element ${this.selector}`);
        app.tap(this.selector);
    }
    async clearValue() {}
    async setValue(value) {
        app.typed.set(this.selector, String(value));
    }
}

globalThis.$ = async (selector) => new FakeElement(selector);
globalThis.driver = {
    async waitUntil(condition) {
        for (let i = 0; i < 5; i += 1) {
            if (await condition()) return true;
        }
        throw new Error('waitUntil condition not met');
    },
    async execute() {},
    async getWindowSize() {
        return { width: 1080, height: 1920 };
    },
    async isKeyboardShown() {
        return false;
    },
    async hideKeyboard() {},
    async terminateApp() {},
    async activateApp() {
        app.reset();
    },
};
globalThis.expect = (actual) => ({
    toBe(expected) {
        if (actual !== expected) throw new Error(`expected ${JSON.stringify(actual)} to be ${JSON.stringify(expected)}`);
    },
});

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
