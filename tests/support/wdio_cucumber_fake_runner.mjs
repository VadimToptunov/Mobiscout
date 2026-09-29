// A device-free WebdriverIO + Cucumber runtime for executing a generated WebdriverIO Cucumber kit.
//
// Installs the fake app (wdio_fake_app.mjs), stands in for '@wdio/cucumber-framework' (a stub
// package in the kit's node_modules whose Given/When/Then register step definitions), loads the
// kit's wdio.conf.js (its beforeScenario hook restarts the app) and step files, then runs every
// scenario of every feature: Background first, Scenario Outlines once per Examples row. A step
// must match EXACTLY one definition — an undefined or ambiguous step fails its scenario, as in
// Cucumber. Prints PASS/FAIL per scenario; exits 1 on any failure.
//
// usage: MOBISCOUT_FAKE_APP=app.json node wdio_cucumber_fake_runner.mjs <kit-dir>

import { mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

import { installFakeApp } from './wdio_fake_app.mjs';

const kit = process.argv[2];
installFakeApp();

// The stub adapter: resolved by the step files' bare import from the kit's node_modules.
const stub = join(kit, 'node_modules', '@wdio', 'cucumber-framework');
mkdirSync(stub, { recursive: true });
writeFileSync(join(stub, 'package.json'), JSON.stringify({ name: '@wdio/cucumber-framework', type: 'module', main: 'index.js' }));
writeFileSync(
    join(stub, 'index.js'),
    [
        'const register = (expression, fn) => globalThis.__mobiscoutSteps.push({ expression, fn });',
        'export const Given = register;',
        'export const When = register;',
        'export const Then = register;',
    ].join('\n'),
);
globalThis.__mobiscoutSteps = [];

// A Cucumber expression as a regex: {string} captures a double- or single-quoted value.
function toRegex(expression) {
    const escaped = expression.replace(/[.*+?^$()|[\]\\]/g, '\\$&');
    return new RegExp(`^${escaped.replace(/\{string\}/g, `(?:"([^"]*)"|'([^']*)')`)}$`);
}

// The Gherkin this suite's generator writes: Feature / Background / Scenario / Scenario Outline
// with an Examples table; step keywords Given/When/Then/And/But.
function parseFeature(text) {
    const feature = { name: '', background: [], scenarios: [] };
    let current = null;
    let table = null;
    for (const raw of text.split('\n')) {
        const line = raw.trim();
        if (!line || line.startsWith('#')) continue;
        let m;
        if ((m = line.match(/^Feature:\s*(.*)$/))) feature.name = m[1];
        else if (line.startsWith('Background:')) current = { steps: feature.background };
        else if ((m = line.match(/^Scenario(?: Outline)?:\s*(.*)$/))) {
            current = { name: m[1], steps: [], examples: null };
            feature.scenarios.push(current);
            table = null;
        } else if (line.startsWith('Examples:')) {
            table = [];
            current.examples = table;
        } else if (line.startsWith('|') && table) {
            table.push(line.slice(1, -1).split('|').map((c) => c.trim()));
        } else if ((m = line.match(/^(Given|When|Then|And|But)\s+(.*)$/))) current.steps.push(m[2]);
    }
    return feature;
}

function expand(scenario) {
    if (!scenario.examples) return [{ name: scenario.name, steps: scenario.steps }];
    const [header, ...rows] = scenario.examples;
    return rows.map((row, i) => ({
        name: `${scenario.name} #${i + 1}`,
        steps: scenario.steps.map((s) => header.reduce((acc, col, j) => acc.replaceAll(`<${col}>`, row[j]), s)),
    }));
}

async function runStep(text) {
    const hits = globalThis.__mobiscoutSteps
        .map((def) => ({ def, m: text.match(toRegex(def.expression)) }))
        .filter((h) => h.m);
    if (hits.length === 0) throw new Error(`undefined step: ${text}`);
    if (hits.length > 1) throw new Error(`ambiguous step: ${text} (${hits.map((h) => h.def.expression).join(' | ')})`);
    const args = [];
    for (let i = 1; i < hits[0].m.length; i += 2) args.push(hits[0].m[i] ?? hits[0].m[i + 1]);
    await hits[0].def.fn(...args);
}

const { config } = await import(pathToFileURL(join(kit, 'wdio.conf.js')).href);
const stepsDir = join(kit, 'features', 'step-definitions');
for (const file of readdirSync(stepsDir).filter((f) => f.endsWith('.steps.js')).sort()) {
    await import(pathToFileURL(join(stepsDir, file)).href);
}

let passed = 0;
let failed = 0;
const featuresDir = join(kit, 'features');
for (const file of readdirSync(featuresDir).filter((f) => f.endsWith('.feature')).sort()) {
    const feature = parseFeature(readFileSync(join(featuresDir, file), 'utf8'));
    for (const scenario of feature.scenarios.flatMap(expand)) {
        const title = `${feature.name} > ${scenario.name}`;
        try {
            if (config.beforeScenario) await config.beforeScenario();
            for (const step of [...feature.background, ...scenario.steps]) await runStep(step);
            passed += 1;
            console.log(`PASS: ${title}`);
        } catch (error) {
            failed += 1;
            console.log(`FAIL: ${title}: ${error.message}`);
        }
    }
}
console.log(`${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : passed ? 0 : 2);
