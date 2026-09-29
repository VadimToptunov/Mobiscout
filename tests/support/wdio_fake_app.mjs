// A device-free WebdriverIO world for executing generated WebdriverIO kits: installs the
// globals the page objects use ($, driver, expect) backed by a fake app model (screens of
// selector strings + transitions). Shared by the Mocha and Cucumber fake runners.
//
// Model JSON ($MOBISCOUT_FAKE_APP): {"start": int, "screens": [[selector, ...], ...],
//                                     "transitions": [[from, selector, to], ...],
//                                     "crashes": [[screen, selector], ...]}  // tapping it kills the app

import { readFileSync } from 'node:fs';

export function installFakeApp() {
    const model = JSON.parse(readFileSync(process.env.MOBISCOUT_FAKE_APP, 'utf8'));
    const app = {
        screens: model.screens.map((s) => new Set(s)),
        transitions: new Map(model.transitions.map(([from, sel, to]) => [`${from}\u0000${sel}`, to])),
        start: model.start ?? 0,
        current: model.start ?? 0,
        typed: new Map(),
        history: [],
        running: true,
        crashes: new Set((model.crashes ?? []).map(([from, sel]) => `${from}\u0000${sel}`)),
        present(sel) {
            if (!this.running) return false;
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
            if (this.crashes.has(`${this.current}\u0000${sel}`)) {
                this.running = false;
                return;
            }
            const next = this.transitions.get(`${this.current}\u0000${sel}`);
            if (next !== undefined && this.validInput()) {
                this.history.push(this.current);
                this.current = next;
                this.typed.clear();
            }
        },
        back() {
            if (this.history.length) this.current = this.history.pop();
            this.typed.clear();
        },
        reset() {
            this.running = true;
            this.history = [];
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
        async back() {
            app.back();
        },
        async queryAppState() {
            return app.running ? 4 : 1; // running in the foreground / not running
        },
    };
    globalThis.expect = (actual) => ({
        toBe(expected) {
            if (actual !== expected) throw new Error(`expected ${JSON.stringify(actual)} to be ${JSON.stringify(expected)}`);
        },
    });
    return app;
}
