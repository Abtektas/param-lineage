// node --test test/*.test.js
// The page's conversion rules against what param_translation.cpp of the target release did with
// every probe value (data/translations): the corrected file must write what an in-place upgrade
// stores, no more and no less.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const A = require('../src/analyze.js');

const data = JSON.parse(fs.readFileSync(path.join(__dirname, '../data/v1.17.0_to_v1.18.0-rc1.json')));
const translations = JSON.parse(fs.readFileSync(path.join(__dirname, `../../data/translations/${data.to.tag}.json`))).parameters;
const TYPE = { i: 'Int32', f: 'Float' };

// {name: value} the import stores for one probe value, besides the probed name itself
function stored(name, probe, value) {
  const out = {};
  const { outcome } = probe;
  const valueOf = (v) => (v === 'stored' ? value : v);
  if (outcome.result === 'stored' && outcome.name !== name) out[outcome.name] = valueOf(outcome.value);
  for (const [other, v] of Object.entries(outcome.also_set || {})) out[other] = valueOf(v);
  return out;
}

// as float32, and -0 as 0: the corrected file writes both as 0
const asFloat32 = (writes) => Object.fromEntries(Object.entries(writes).map(([n, v]) => [n, Math.fround(v) + 0]));

test('every conversion rule writes what the in-place upgrade stores', () => {
  const migrated = Object.entries(data.notes).filter(([, note]) => note.kind === 'migrated');
  assert.ok(migrated.length > 0);
  for (const [name, note] of migrated) {
    // only values of the type the file was saved with
    const probes = translations[name].filter((p) => p.stored.type === TYPE[data.removedMeta[name].t]);
    let compared = 0;
    for (const probe of probes) {
      for (const value of probe.stored.values) {
        const rule = Object.fromEntries(A.applyRule(note.rule, value, new Map(), data.target).map((w) => [w.name, w.value]));
        assert.deepEqual(asFloat32(rule), asFloat32(stored(name, probe, value)), `${name} = ${value}`);
        compared++;
      }
    }
    assert.ok(compared > 0, name);
  }
});

test('the type fixes write what the in-place upgrade stores', () => {
  for (const name of Object.keys(data.typeRules)) {
    const probes = translations[name].filter((p) => p.stored.type === TYPE[data.source[name][0]]);
    assert.ok(probes.length > 0, name);
    for (const probe of probes) {
      for (const value of probe.stored.values) {
        // the way QGroundControl saves a float
        const report = A.analyze(`1\t1\t${name}\t${value.toFixed(18)}\t9`, data);
        const fix = report.findings.find((f) => f.category === 'typeFix');
        assert.equal(probe.outcome.name, name);
        assert.equal(fix.newValue, probe.outcome.value, `${name} = ${value}`);
      }
    }
  }
});
