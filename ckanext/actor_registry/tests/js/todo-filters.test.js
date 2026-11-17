'use strict';

// The To do filters: a chosen tag or organisation applies at once; if the page's question about unsaved choices
// keeps the visitor, the list goes back to "Add …". The Filter button is hidden (Enter applies the search).

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SOURCE = fs.readFileSync(path.join(__dirname, '..', '..', 'assets', 'js', 'todo-filters.js'), 'utf8');

function host(extra) {
  const listeners = {};
  return Object.assign({
    addEventListener(name, handler) { (listeners[name] = listeners[name] || []).push(handler); },
    removeEventListener(name, handler) { listeners[name] = (listeners[name] || []).filter((h) => h !== handler); },
    fire(name, event) { (listeners[name] || []).slice().forEach((handler) => handler(event)); }
  }, extra);
}

const tag = host({ value: '' });
const org = host({ value: '' });
const button = host({ hidden: false });
let keep = false;
let submitted = 0;
let sent = null;
const form = host({
  querySelectorAll: () => [tag, org],
  querySelector: () => button,
  requestSubmit() {
    const event = { defaultPrevented: keep };
    this.fire('submit', event);
    if (!event.defaultPrevented) { submitted += 1; sent = [tag, org].filter((s) => !s.disabled).map((s) => s.value); }
  }
});
const timers = [];
vm.runInNewContext(SOURCE, { document: { readyState: 'complete', querySelectorAll: () => [form] }, setTimeout: (f) => timers.push(f) });
assert.strictEqual(button.hidden, true);

// "Add a tag…" itself does nothing.
tag.fire('change');
assert.strictEqual(submitted, 0);

// A tag applies at once.
tag.value = 'water';
tag.fire('change');
timers.splice(0).forEach((f) => f());
assert.strictEqual(submitted, 1);
assert.strictEqual(tag.value, 'water');
// The organisation list, left at "Add …", was not sent, and is back on afterwards.
assert.deepStrictEqual(sent, ['water']);
assert.strictEqual(org.disabled, false);

// Kept on the page by the question: back to "Add a tag…".
keep = true;
tag.value = 'air';
tag.fire('change');
timers.splice(0).forEach((f) => f());
assert.strictEqual(submitted, 1);
assert.strictEqual(tag.value, '');
