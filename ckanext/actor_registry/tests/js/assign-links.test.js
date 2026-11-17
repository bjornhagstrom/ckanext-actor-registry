'use strict';

// The To do list: one Save saves the rows' own choices and the bar's choices on the ticked rows; its button says how
// many datasets that is. Leaving with anything unsaved asks, with what would be lost. A save comes back where the
// page was. "Create new…" adds a publisher or contact point from any list.

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SOURCE = fs.readFileSync(path.join(__dirname, '..', '..', 'assets', 'js', 'assign-links.js'), 'utf8');

function host(extra) {
  const listeners = {};
  return Object.assign({
    attrs: {},
    getAttribute(name) { return this.attrs[name] === undefined ? null : this.attrs[name]; },
    hasAttribute(name) { return this.attrs[name] !== undefined; },
    addEventListener(name, handler) { (listeners[name] = listeners[name] || []).push(handler); },
    removeEventListener() {},
    fire(name, event) { (listeners[name] || []).forEach((handler) => handler(event)); }
  }, extra);
}

const classes = () => { const set = new Set(); return { add: (c) => set.add(c), remove: (c) => set.delete(c), contains: (c) => set.has(c) }; };

// The Save button, the rows' marks and the question when leaving.
(function () {
  const bar = (name) => host({ name, value: '', attrs: { 'data-assign-choice': name.replace(/_(top|bottom)$/, '') } });
  const barTop = bar('publisher_actor_id_top');
  const barBottom = bar('publisher_actor_id_bottom');
  const rowSelectA = host({ name: 'publisher_for_a', value: '' });
  const rowSelectB = host({ name: 'publisher_for_b', value: '' });
  const rowContactB = host({ name: 'contact_point_for_b', value: '' });
  const boxA = host({ checked: false, value: 'a' });
  const boxB = host({ checked: false, value: 'b' });
  const badgeA = host({ hidden: true });
  const badgeB = host({ hidden: true });
  const rowA = host({ attrs: { 'data-assign-row': 'a' }, classList: classes(),
    querySelector: (s) => ({ '[data-assign-dataset]': boxA, '[data-unsaved-badge]': badgeA }[s]) });
  const rowB = host({ attrs: { 'data-assign-row': 'b' }, classList: classes(),
    querySelector: (s) => ({ '[data-assign-dataset]': boxB, '[data-unsaved-badge]': badgeB }[s]) });
  const saves = ['top', 'bottom'].map((value) => host({ value, textContent: 'Save', disabled: false, attrs: {
    'data-i18n-none': 'Nothing to save yet', 'data-i18n-pick': 'Choose for the selected',
    'data-i18n-one': 'Save (1 dataset)', 'data-i18n-many': 'Save ({count} datasets)' } }));
  const form = host({
    attrs: { 'data-i18n-leave': 'Not saved ({details}). Leave?',
      'data-i18n-chosen-one': '1 row with a choice', 'data-i18n-chosen-many': '{count} rows with a choice',
      'data-i18n-selected-one': '1 selected row', 'data-i18n-selected-many': '{count} selected rows' },
    querySelectorAll(selector) {
      return {
        '[data-assign-dataset]': [boxA, boxB], '[data-assign-choice]': [barTop, barBottom], '[data-assign-save]': saves,
        select: [barTop, barBottom, rowSelectA, rowSelectB, rowContactB], '[data-assign-row]': [rowA, rowB]
      }[selector] || [];
    }
  });
  const asked = [];
  const docListeners = {};
  const document = {
    readyState: 'complete', querySelectorAll: () => [form],
    addEventListener(name, handler) { (docListeners[name] = docListeners[name] || []).push(handler); }
  };
  const window = { confirm(text) { asked.push(text); return false; } };
  vm.runInNewContext(SOURCE, { document, window });
  const texts = () => saves.map((button) => [button.textContent, button.disabled]);

  // Nothing yet: nothing to save.
  assert.deepStrictEqual(texts(), [['Nothing to save yet', true], ['Nothing to save yet', true]]);
  // A ticked row with nothing in the bar: the button says what to do.
  boxA.checked = true;
  boxA.fire('change');
  assert.deepStrictEqual(texts()[0], ['Choose for the selected', true]);
  assert.ok(rowA.classList.contains('table-active') && !rowB.classList.contains('table-active'));
  // A choice in the bar goes to the ticked row; the other bar follows.
  barTop.value = 'actor-1';
  barTop.fire('change');
  assert.strictEqual(barBottom.value, 'actor-1');
  assert.deepStrictEqual(texts(), [['Save (1 dataset)', false], ['Save (1 dataset)', false]]);
  // A row's own choices count too, a row once however many choices it has.
  rowSelectB.value = 'actor-2';
  rowSelectB.fire('change');
  rowContactB.value = 'cp-1';
  rowContactB.fire('change');
  assert.deepStrictEqual(texts()[0], ['Save (2 datasets)', false]);
  assert.ok(rowB.classList.contains('table-info'));
  assert.strictEqual(badgeB.hidden, false);
  assert.strictEqual(badgeA.hidden, true);
  // A ticked row with a choice of its own is still one dataset.
  rowSelectA.value = 'actor-3';
  rowSelectA.fire('change');
  assert.deepStrictEqual(texts()[0], ['Save (2 datasets)', false]);
  // The 7b case of the test: a row's choice with the row ticked and nothing in the bar is still saved.
  barTop.value = '';
  barTop.fire('change');
  rowSelectB.value = '';
  rowSelectB.fire('change');
  rowContactB.value = '';
  rowContactB.fire('change');
  assert.deepStrictEqual(texts()[0], ['Save (1 dataset)', false]);

  // A link away asks, saying only what there is; no keeps the page.
  const link = { getAttribute: () => '/dataset/x', target: '' };
  const click = { target: { closest: () => link }, prevented: false, preventDefault() { this.prevented = true; } };
  docListeners.click.forEach((handler) => handler(click));
  assert.deepStrictEqual(asked, ['Not saved (1 row with a choice, 1 selected row). Leave?']);
  assert.strictEqual(click.prevented, true);
  boxB.checked = true;
  boxB.fire('change');
  rowSelectA.value = '';
  rowSelectA.fire('change');
  docListeners.click.forEach((handler) => handler(click));
  assert.strictEqual(asked[1], 'Not saved (2 selected rows). Leave?');

  // A link within the page does not ask.
  const anchor = { target: { closest: () => ({ getAttribute: () => '#top', target: '' }) }, preventDefault() { throw new Error('no'); } };
  docListeners.click.forEach((handler) => handler(anchor));
  assert.strictEqual(asked.length, 2);

  // Nothing unsaved: no question.
  boxA.checked = false;
  boxB.checked = false;
  boxA.fire('change');
  const again = { target: { closest: () => link }, preventDefault() { throw new Error('no'); } };
  docListeners.click.forEach((handler) => handler(again));
  assert.strictEqual(asked.length, 2);
})();

// A save comes back where the page was; the messages float in view when the list's top is out of sight.
(function () {
  const store = {};
  const sessionStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; } };
  const form = host({ querySelectorAll: () => [] });
  const messages = host({ children: [1], classList: classes(), getBoundingClientRect: () => ({ top: 400, bottom: 500 }) });
  const scrolled = [];
  const timers = [];
  // The browser is still at the list's top (#todo-list, scrollY 0) when the messages are measured, as with a theme's
  // smooth scrolling: they count as out of view all the same, since the page is going to 1234.
  const window = { sessionStorage, scrollY: 0, innerHeight: 800, location: { pathname: '/actor-registry/todo' },
    scrollTo: (options) => scrolled.push(options.top), confirm: () => true };
  const document = { readyState: 'complete', querySelectorAll: () => [form], documentElement: { scrollHeight: 5000 },
    querySelector: (s) => (s === '[data-todo-messages]' ? messages : null), addEventListener() {} };
  vm.runInNewContext(SOURCE, { document, window, JSON, setTimeout: (f) => timers.push(f) });
  assert.deepStrictEqual(scrolled, []);  // nothing saved yet: the page opens as the browser opens it
  window.scrollY = 1234;
  form.fire('submit');
  const saved = JSON.parse(store['actor-registry-todo-scroll']);
  assert.deepStrictEqual([saved.path, saved.y, typeof saved.at], ['/actor-registry/todo', 1234, 'number']);
  window.scrollY = 0;
  // The next page: back to 1234, the key used up, the messages floating until the timer or a click.
  vm.runInNewContext(SOURCE, { document, window, JSON, setTimeout: (f) => timers.push(f) });
  assert.deepStrictEqual(scrolled, [1234]);
  assert.ok(!('actor-registry-todo-scroll' in store));
  assert.ok(messages.classList.contains('todo-messages-float'));
  timers.forEach((f) => f());
  assert.ok(!messages.classList.contains('todo-messages-float'));
  // Another page's position, or an old one from a save that never came back, is not used.
  store['actor-registry-todo-scroll'] = JSON.stringify({ path: '/elsewhere', y: 50, at: Date.now() });
  vm.runInNewContext(SOURCE, { document, window, JSON, setTimeout: (f) => timers.push(f) });
  store['actor-registry-todo-scroll'] = JSON.stringify({ path: '/actor-registry/todo', y: 50, at: Date.now() - 600000 });
  vm.runInNewContext(SOURCE, { document, window, JSON, setTimeout: (f) => timers.push(f) });
  assert.deepStrictEqual(scrolled, [1234]);
  // Messages in view where the page ends up do not float; a position past the end is cut to the end.
  messages.getBoundingClientRect = () => ({ top: 4300, bottom: 4400 });
  store['actor-registry-todo-scroll'] = JSON.stringify({ path: '/actor-registry/todo', y: 9000, at: Date.now() });
  vm.runInNewContext(SOURCE, { document, window, JSON, setTimeout: (f) => timers.push(f) });
  assert.deepStrictEqual(scrolled, [1234, 4200]);
  assert.ok(!messages.classList.contains('todo-messages-float'));
  const broken = Object.assign({}, window);
  Object.defineProperty(broken, 'sessionStorage', { get() { throw new Error('blocked'); } });
  vm.runInNewContext(SOURCE, { document, window: broken, JSON, setTimeout: (f) => timers.push(f) });
  form.fire('submit');
})();

// Leaving: a click that opens a new tab does not ask, the page's own save never asks, another form asks,
// closing the tab gets the browser's question, and an OK is not given for a click that stays on the page.
(function () {
  const box = host({ checked: true });
  const form = host({
    attrs: { 'data-i18n-leave': 'Leave? ({details})', 'data-i18n-selected-one': '1 selected', 'data-i18n-selected-many': '{count} selected' },
    querySelectorAll: (selector) => ({ '[data-assign-dataset]': [box] }[selector] || [])
  });
  const asked = [];
  const doc = {}; const win = {};
  const document = { readyState: 'complete', querySelectorAll: () => [form],
    addEventListener(name, handler) { (doc[name] = doc[name] || []).push(handler); } };
  const window = { confirm(text) { asked.push(text); return false; },
    addEventListener(name, handler) { (win[name] = win[name] || []).push(handler); } };
  const source = fs.readFileSync(path.join(__dirname, '..', '..', 'assets', 'js', 'assign-links.js'), 'utf8');
  vm.runInNewContext(source, { document, window });
  const link = { getAttribute: () => '/dataset/x', target: '' };
  const click = (extra) => Object.assign({ target: { closest: () => link }, button: 0, prevented: false,
    preventDefault() { this.prevented = true; } }, extra);
  for (const modifier of [{ metaKey: true }, { ctrlKey: true }, { shiftKey: true }, { button: 1 }]) {
    const event = click(modifier);
    doc.click.forEach((handler) => handler(event));
    assert.strictEqual(event.prevented, false);
  }
  assert.deepStrictEqual(asked, []);
  // The page's own form is not asked about; another form is.
  const own = { target: form, preventDefault() { throw new Error('no'); } };
  doc.submit.forEach((handler) => handler(own));
  const other = { target: host(), prevented: false, preventDefault() { this.prevented = true; } };
  doc.submit.forEach((handler) => handler(other));
  assert.strictEqual(other.prevented, true);
  assert.deepStrictEqual(asked, ['Leave? (1 selected)']);
  // Closing the tab: the browser's own question.
  const unload = { prevented: false, preventDefault() { this.prevented = true; } };
  win.beforeunload.forEach((handler) => handler(unload));
  assert.strictEqual(unload.prevented, true);
  box.checked = false;
  const nothing = { preventDefault() { throw new Error('no'); } };
  win.beforeunload.forEach((handler) => handler(nothing));
})();

// "Create new…": an option in each list of its kind; saving adds the new one to every such list and chooses it where it
// was asked for; Cancel goes back to what was chosen before, also in a bar that got its choice from the other bar.
(async function () {
  function select(name, kind, choice, value) {
    const options = [];
    const s = host({ name, value: value || '', tagName: 'SELECT', options,
      attrs: Object.assign({ 'data-assign-kind': kind }, choice ? { 'data-assign-choice': choice } : {}),
      appendChild(option) { options.push(option); },
      insertBefore(option, before) { options.splice(options.indexOf(before), 0, option); },
      querySelector: (selector) => options.find((o) => selector.includes(o.value)),
      dispatchEvent() { this.fire('change'); }, focus() {} });
    return s;
  }
  const top = select('publisher_actor_id_top', 'publisher', 'publisher_actor_id');
  const bottom = select('publisher_actor_id_bottom', 'publisher', 'publisher_actor_id');
  const row = select('publisher_for_a', 'publisher');
  const contact = select('contact_point_for_a', 'contact_point');
  const name = host({ value: '', tagName: 'INPUT', attrs: { 'data-field': 'name' }, focus() {} });
  const error = host({ hidden: true });
  const save = host({ disabled: false });
  const cancel = host();
  const dialog = host({ attrs: { 'data-create-dialog': 'publisher', 'data-endpoint': '/actors/quick-create', 'data-i18n-failed': 'Failed' },
    open: false, showModal() { this.open = true; }, close() { this.open = false; },
    querySelector: (selector) => ({ '[data-create-error]': error, '[data-field="name"]': name, '[data-create-save]': save,
      '[data-create-cancel]': cancel }[selector] || null),
    querySelectorAll: (selector) => (selector === '[data-field]' ? [name] : []) });
  const form = host({
    attrs: { 'data-i18n-create-new': 'Create new…' },
    querySelectorAll(selector) {
      if (selector === '[data-assign-choice]') return [top, bottom];
      if (selector === 'select') return [top, bottom, row, contact];
      if (selector === 'select[data-assign-kind]') return [top, bottom, row, contact];
      if (selector === 'select[data-assign-kind="publisher"]') return [top, bottom, row];
      return [];
    }
  });
  let response = { ok: true, json: async () => ({ success: true, actor: { id: 'new-1', name: 'New Board' } }) };
  const posted = [];
  const document = { readyState: 'complete', querySelectorAll: (s) => (s === '[data-create-dialog]' ? [dialog] : [form]),
    querySelector: () => null, createElement: () => ({}) };
  const sandbox = { document, window: { confirm: () => true }, Event: function (type) { this.type = type; },
    FormData: function () { this.entries = []; this.append = (k, v) => this.entries.push([k, v]); },
    fetch: (url, options) => { posted.push([url, options.body.entries]); return Promise.resolve(response); } };
  const source = fs.readFileSync(path.join(__dirname, '..', '..', 'assets', 'js', 'assign-links.js'), 'utf8');
  vm.runInNewContext(source, sandbox);
  assert.deepStrictEqual([top, bottom, row].map((s) => s.options.map((o) => o.textContent)), [['Create new…'], ['Create new…'], ['Create new…']]);
  assert.strictEqual(contact.options.length, 0);  // no dialog for contact points on this page

  // Cancel in the bottom bar after choosing in the top one: both keep the earlier choice.
  top.value = 'old';
  top.fire('change');
  assert.strictEqual(bottom.value, 'old');
  bottom.value = '__new__';
  bottom.fire('change');
  assert.strictEqual(dialog.open, true);
  cancel.fire('click');
  assert.strictEqual(dialog.open, false);
  assert.strictEqual(bottom.value, 'old');
  assert.strictEqual(top.value, 'old');

  // Save: posted to the quick create, added to every publisher list before "Create new…", chosen in the row.
  row.value = '__new__';
  row.fire('change');
  name.value = 'New Board';
  save.fire('click');
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepStrictEqual(posted, [['/actors/quick-create', [['name', 'New Board']]]]);
  assert.deepStrictEqual(row.options.map((o) => o.value), ['new-1', '__new__']);
  assert.deepStrictEqual(top.options.map((o) => o.textContent), ['New Board', 'Create new…']);
  assert.strictEqual(row.value, 'new-1');
  assert.strictEqual(dialog.open, false);

  // A refusal is shown in the dialog, which stays open.
  response = { ok: false, json: async () => ({ success: false, error: 'Name is required.' }) };
  row.value = '__new__';
  row.fire('change');
  name.value = 'x';
  save.fire('click');
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  assert.strictEqual(error.hidden, false);
  assert.strictEqual(error.textContent, 'Name is required.');
  assert.strictEqual(dialog.open, true);
  cancel.fire('click');

  // A late answer: saved from the row, cancelled, then opened from the bottom bar. The record is
  // added to the lists, but chosen nowhere, and the bottom bar's dialog stays open.
  let answer;
  response = new Promise((resolve) => { answer = resolve; });
  sandbox.fetch = () => response;
  row.value = '__new__';
  row.fire('change');
  name.value = 'Late Board';
  save.fire('click');
  cancel.fire('click');
  const rowBefore = row.value;
  bottom.value = '__new__';
  bottom.fire('change');
  assert.strictEqual(dialog.open, true);
  assert.strictEqual(save.disabled, false);  // the new opening can save at once
  answer({ ok: true, json: async () => ({ success: true, actor: { id: 'late-1', name: 'Late Board' } }) });
  for (let i = 0; i < 4; i += 1) await new Promise((resolve) => setImmediate(resolve));
  assert.ok(row.options.some((o) => o.value === 'late-1'));
  assert.strictEqual(row.value, rowBefore);
  assert.notStrictEqual(bottom.value, 'late-1');
  assert.notStrictEqual(top.value, 'late-1');
  assert.strictEqual(dialog.open, true);

  // A late refusal is not shown in the dialog's next opening.
  cancel.fire('click');
  response = new Promise((resolve) => { answer = resolve; });
  row.value = '__new__';
  row.fire('change');
  name.value = 'Late refusal';
  save.fire('click');
  cancel.fire('click');
  bottom.value = '__new__';
  bottom.fire('change');
  answer({ ok: false, json: async () => ({ success: false, error: 'Too late.' }) });
  for (let i = 0; i < 4; i += 1) await new Promise((resolve) => setImmediate(resolve));
  assert.strictEqual(error.hidden, true);
  assert.strictEqual(dialog.open, true);
})().catch((problem) => { console.error(problem); process.exitCode = 1; });
