'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function host(extra) {
  const listeners = {};
  return Object.assign({
    hidden: false,
    attrs: {},
    getAttribute(name) { return this.attrs[name] || null; },
    setAttribute(name, value) { this.attrs[name] = value; },
    addEventListener(name, handler) { (listeners[name] = listeners[name] || []).push(handler); },
    fire(name) { (listeners[name] || []).forEach((handler) => handler()); }
  }, extra);
}

function box(value, checked) {
  return host({ value, checked, disabled: false });
}

function build(total) {
  const plainInputs = Array.from({ length: total }, (_, i) => box('id' + i, false));
  const boxes = Array.from({ length: total }, (_, i) => box('id' + i, true));
  const master = host({ checked: true, indeterminate: false });
  const posted = [];
  const rows = Array.from({ length: total }, (_, i) => host({ attrs: { 'data-title': 'Set ' + (total - i) } }));
  const headings = ['title', 'org'].map((key) => host({ attrs: { 'data-sort': key }, parentNode: host(), querySelector: () => host({ textContent: '' }) }));
  const body = host({ querySelectorAll: () => rows.slice(), appendChild(row) { this.moved = (this.moved || []).concat([row]); } });
  const includeList = host({
    hidden: true,
    querySelector: (selector) => ({ '[data-include-master]': master, tbody: body }[selector]),
    querySelectorAll: (selector) => (selector === '[data-include-box]' ? boxes : (selector === '[data-sort]' ? headings : []))
  });
  const parts = {
    '[data-large-details]': host({
      attrs: { 'data-i18n-count': '{included} av {total} ingår.', 'data-i18n-none': 'Ingen ingår.' },
      querySelector: (selector) => ({ '[data-exclude-list]': parts['[data-exclude-list]'], '[data-include-list]': includeList }[selector])
    }),
    '[data-exclude-list]': host({ querySelectorAll: () => plainInputs }),
    '[data-large-group]': host({ textContent: 'All included' }),
    '[data-large-help]': host({ attrs: { 'data-i18n-js': 'Clear the ones' }, textContent: 'Tick the ones' }),
    '[data-apply-button]': host({ textContent: 'Apply to all 3 datasets, except those left out', disabled: false,
      attrs: { 'data-i18n-one': 'Apply to {count} dataset', 'data-i18n-many': 'Apply to {count} datasets', 'data-i18n-none': 'Select at least one dataset first' } })
  };
  const form = host({
    querySelector: (selector) => parts[selector],
    querySelectorAll: () => [],
    appendChild(child) { posted.push(child); }
  });
  return { form, parts, plainInputs, boxes, master, posted, includeList, headings, body, rows };
}

function load(scene) {
  const document = {
    readyState: 'complete',
    querySelectorAll: () => [scene.form],
    createElement: () => ({ setAttribute() {} })
  };
  const source = fs.readFileSync(path.join(__dirname, '..', '..', 'assets', 'js', 'migrate-select.js'), 'utf8');
  const sandbox = { document, module: { exports: {} }, Intl };
  vm.runInNewContext(source, sandbox);
  return sandbox.module.exports;
}

const scene = build(3);
const exported = load(scene);

// The script takes over: the plain "leave out" boxes are off and not posted, the table shows.
assert.strictEqual(scene.parts['[data-exclude-list]'].hidden, true);
assert.ok(scene.plainInputs.every((input) => input.disabled));
assert.strictEqual(scene.includeList.hidden, false);
assert.strictEqual(scene.parts['[data-large-help]'].textContent, 'Clear the ones');
assert.strictEqual(scene.parts['[data-large-group]'].textContent, '3 av 3 ingår.');
assert.strictEqual(scene.master.checked, true);

// One box in the heading: none, then some (in between), then all.
scene.master.checked = false;
scene.master.fire('change');
assert.ok(scene.boxes.every((b) => !b.checked));
assert.strictEqual(scene.parts['[data-large-group]'].textContent, 'Ingen ingår.');
assert.strictEqual(scene.parts['[data-apply-button]'].disabled, true);
assert.strictEqual(scene.parts['[data-apply-button]'].textContent, 'Select at least one dataset first');
scene.boxes[1].checked = true;
scene.boxes[1].fire('change');
assert.strictEqual(scene.master.indeterminate, true);
assert.strictEqual(scene.master.checked, false);
assert.strictEqual(scene.parts['[data-large-group]'].textContent, '1 av 3 ingår.');
assert.strictEqual(scene.parts['[data-apply-button]'].textContent, 'Apply to 1 dataset');
assert.strictEqual(scene.parts['[data-apply-button]'].disabled, false);

// Only the datasets that are not ticked are posted as exclude_ids.
scene.form.fire('submit');
assert.deepStrictEqual(scene.posted.map((input) => [input.name, input.value]), [['exclude_ids', 'id0'], ['exclude_ids', 'id2']]);

// All again: nothing is posted, and the box in the heading is ticked.
scene.posted.length = 0;
scene.master.checked = true;
scene.master.fire('change');
assert.strictEqual(scene.master.indeterminate, false);
assert.strictEqual(scene.parts['[data-apply-button]'].textContent, 'Apply to 3 datasets');
scene.form.fire('submit');
assert.strictEqual(scene.posted.length, 0);

// A heading sorts the rows; the same heading again reverses them.
scene.headings[0].fire('click');
assert.deepStrictEqual(scene.body.moved.map((row) => row.getAttribute('data-title')), ['Set 1', 'Set 2', 'Set 3']);
scene.body.moved = [];
scene.headings[0].fire('click');
assert.deepStrictEqual(scene.body.moved.map((row) => row.getAttribute('data-title')), ['Set 3', 'Set 2', 'Set 1']);

// The comparison: numbers as numbers, text as Swedish text (å, ä, ö last), an empty cell last.
const row = (value) => ({ getAttribute: () => value });
const order = (values) => values.map(row).sort(exported.compareBy('x')).map((r) => r.getAttribute());
assert.deepStrictEqual(order(['Set 10', 'Set 2', '', 'Äng', 'Zon', 'Ada']), ['Ada', 'Set 2', 'Set 10', 'Zon', 'Äng', '']);
console.log('ok');
