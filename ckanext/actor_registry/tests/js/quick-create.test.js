'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  return {
    children: [], className: '', textContent: '',
    appendChild(child) { this.children.push(child); },
    replaceChildren() { this.children = []; }
  };
}

const preview = element();
const listeners = {};
const select = {
  selectedOptions: [],
  addEventListener(name, handler) { listeners[name] = handler; }
};
const root = {
  dataset: {
    i18nEmailLabel: 'Email',
    i18nPhoneLabel: 'Phone',
    i18nUrlLabel: 'URL',
    i18nSelectHint: 'Select a contact point to see its details here.'
  },
  querySelector(selector) {
    if (selector === 'select[name="contact_point_ids"]') return select;
    if (selector === '[data-contactpoints-preview]') return preview;
    return null;
  }
};
let jqueryEvents = '';
let jqueryHandler;
function jquery() {
  return {on(events, handler) { jqueryEvents = events; jqueryHandler = handler; }};
}

const context = {
  window: {jQuery: jquery},
  document: {
    readyState: 'complete',
    querySelectorAll() { return [root]; },
    createElement() { return element(); },
    createTextNode(text) { return {textContent: text}; }
  }
};
vm.createContext(context);
const source = fs.readFileSync(
  path.join(__dirname, '../../assets/js/quick-create.js'), 'utf8'
);
vm.runInContext(source, context);

assert.match(jqueryEvents, /change\.actorRegistryPreview/);
assert.match(jqueryEvents, /select2:select\.actorRegistryPreview/);
assert.match(jqueryEvents, /select2:unselect\.actorRegistryPreview/);
assert.equal(typeof jqueryHandler, 'function');

select.selectedOptions = [{
  textContent: 'Testkontakt',
  dataset: {
    email: 'test@skelleftea.se',
    phone: '+46 910 12 34 56',
    url: 'https://www.skelleftea.se/'
  }
}];
jqueryHandler();

assert.equal(preview.children.length, 1);
assert.equal(preview.children[0].children[0].children[0].textContent, 'Testkontakt');
assert.equal(preview.children[0].children.length, 4);
console.log('Kontaktpunktsförhandsvisning via jQuery/Select2: OK');
