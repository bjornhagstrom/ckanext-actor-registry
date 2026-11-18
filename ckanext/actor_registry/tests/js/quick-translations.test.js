'use strict';

// The quick panels in the dataset form send a name in another language only when the editor changed it, so that a
// name the panel could not show (an inactive choice) or one changed meanwhile on another page is never removed (0.7.0).

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element(extra) {
  const handlers = {};
  return Object.assign({
    children: [], className: '', textContent: '', value: '', hidden: false, disabled: false, dataset: {},
    appendChild(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
    addEventListener(name, handler) { handlers[name] = handler; },
    click() { return handlers.click && handlers.click(); },
    fire(name) { return handlers[name] && handlers[name](); },
    focus() {},
    dispatchEvent() {}
  }, extra || {});
}

function run(scriptName, widget, prefix, fieldNames, selectName) {
  const fields = {};
  fieldNames.forEach(function (name) { fields[name] = element({dataset: {field: name}}); });
  const translation = element({dataset: {translation: 'en'}});
  const form = element({
    querySelectorAll(selector) {
      if (selector === '[data-field]') return Object.values(fields);
      if (selector === '[data-translation]') return [translation];
      return [];
    },
    querySelector(selector) {
      const match = /^\[data-field="(.+)"\]$/.exec(selector);
      if (match) return fields[match[1]];
      return null;
    }
  });
  const option = element({value: 'id-1', textContent: 'En testutgivare', dataset: {name: 'En testutgivare'}});
  const select = element({
    options: [option], selectedOptions: [option], selectedIndex: 0,
    querySelector() { return option; },
    appendChild() {}
  });
  const parts = {panel: element(), 'panel-title': element(), toggle: element(), cancel: element(), save: element(),
                 form: form, error: element(), preview: element()};
  const root = element({
    dataset: {endpoint: '/create', editEndpointTemplate: '/edit/__ID__', i18nSaveFailed: 'Kunde inte sparas.'},
    querySelector(selector) {
      if (selector === 'select[name="' + selectName + '"]') return select;
      const match = new RegExp('^\\[data-' + prefix + '-(.+)\\]$').exec(selector);
      return match ? parts[match[1]] || null : null;
    }
  });
  const sent = [];
  const network = {down: false};
  const context = {
    window: {},
    CSS: {escape: function (value) { return value; }},
    Event: function () {},
    FormData: function () { this.entries = []; this.append = function (k, v) { this.entries.push([k, v]); }; },
    fetch: function (url, options) {
      // The browser's own TypeError ("Failed to fetch"), made in the script's realm so that instanceof sees it.
      if (network.down) return Promise.reject(vm.runInContext('new TypeError("Failed to fetch")', context));
      sent.push(Object.fromEntries(options.body.entries));
      return Promise.resolve({ok: true, redirected: false, url: url,
        text: function () { return Promise.resolve(JSON.stringify({success: true, actor: {name: 'En testutgivare'},
          contact_point: {name: 'En testutgivare'}})); }});
    },
    document: {
      readyState: 'complete',
      querySelectorAll(selector) { return selector === '[data-' + widget + ']' ? [root] : []; },
      createElement() { return element(); },
      createTextNode(text) { return {textContent: text}; }
    }
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../../assets/js/' + scriptName), 'utf8'), context);

  function edit() {
    select.fire('change');
    const find = function (node) {
      if (node.textContent === 'Edit' && node.children.length === 0) return node;
      for (const child of node.children) { const found = find(child); if (found) return found; }
      return null;
    };
    find(parts.preview).click();
  }
  return {option, translation, fields, save: parts.save, error: parts.error, edit, sent, network};
}

async function check(scriptName, widget, prefix, fieldNames, selectName) {
  const panel = run(scriptName, widget, prefix, fieldNames, selectName);
  const settle = function () { return new Promise(function (resolve) { setTimeout(resolve, 0); }); };

  // An option with a name in English: the panel shows it, and sends it only when changed.
  panel.option.dataset.translations = JSON.stringify({en: {name: 'A test publisher'}});
  panel.edit();
  assert.strictEqual(panel.fields.name.value, 'En testutgivare');
  assert.strictEqual(panel.translation.value, 'A test publisher');
  panel.save.click();
  await settle();
  assert.strictEqual(panel.sent[0].translations_form, undefined, scriptName + ': an unchanged name is not sent');

  panel.edit();
  panel.translation.value = 'A test publisher 2';
  panel.save.click();
  await settle();
  assert.strictEqual(panel.sent[1].translations_form, '1');
  assert.strictEqual(panel.sent[1]['translation_name-en'], 'A test publisher 2');

  // An option without data-translations (as an inactive choice once was): nothing is sent, so nothing is removed.
  delete panel.option.dataset.translations;
  panel.edit();
  assert.strictEqual(panel.translation.value, '');
  panel.save.click();
  await settle();
  assert.strictEqual(panel.sent[2].translations_form, undefined, scriptName + ': an empty, unchanged name is not sent');

  // A network error shows the panel's own message in the page's language, not the browser's English text.
  panel.network.down = true;
  panel.edit();
  panel.save.click();
  await settle();
  assert.strictEqual(panel.error.textContent, 'Kunde inte sparas.', scriptName + ': a network error is shown translated');
}

(async function () {
  await check('actor-quick-create.js', 'actors-widget', 'actors',
              ['name', 'actor_kind', 'identifier', 'identifier_scheme', 'url'], 'publisher_actor_id');
  await check('quick-create.js', 'contactpoints-widget', 'contactpoints',
              ['name', 'actor_id', 'email', 'phone', 'url'], 'contact_point_ids');
})().catch(function (problem) { console.error(problem); process.exitCode = 1; });
