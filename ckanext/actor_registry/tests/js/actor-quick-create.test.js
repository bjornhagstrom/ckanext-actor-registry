'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element() {
  return {
    children: [], className: '', textContent: '', href: '',
    appendChild(child) { this.children.push(child); },
    replaceChildren() { this.children = []; }
  };
}

const preview = element();
const listeners = {};
const select = {
  options: [], selectedIndex: -1,
  addEventListener(name, handler) { listeners[name] = handler; }
};
const root = {
  dataset: {
    i18nKindLabel: 'Kind',
    i18nKindPerson: 'Person',
    i18nKindOrganization: 'Organization',
    i18nIdentifierLabel: 'Identifier',
    i18nDescriptionLabel: 'Description',
    i18nUrlLabel: 'URL'
  },
  querySelector(selector) {
    if (selector === 'select[name="publisher_actor_id"]') return select;
    if (selector === '[data-actors-preview]') return preview;
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
  path.join(__dirname, '../../assets/js/actor-quick-create.js'), 'utf8'
);
vm.runInContext(source, context);

assert.match(jqueryEvents, /change\.actorRegistryPreview/);
assert.match(jqueryEvents, /select2:select\.actorRegistryPreview/);
assert.match(jqueryEvents, /select2:unselect\.actorRegistryPreview/);
assert.equal(typeof jqueryHandler, 'function');

select.options = [{
  value: 'actor-1',
  textContent: 'Gymnasieförvaltningen',
  dataset: {
    kind: 'organization',
    identifier: '212000-2643',
    description: 'Testutgivare',
    url: 'https://www.skelleftea.se/'
  }
}];
select.selectedIndex = 0;
jqueryHandler();

assert.equal(preview.children.length, 1);
assert.equal(preview.children[0].children[0].children[0].textContent, 'Gymnasieförvaltningen');
assert.equal(preview.children[0].children[1].textContent, 'Kind: Organization');
assert.equal(preview.children[0].children[2].textContent, 'Identifier: 212000-2643');
assert.equal(preview.children[0].children[3].textContent, 'Description: Testutgivare');
assert.equal(preview.children[0].children[4].children[0].href, 'https://www.skelleftea.se/');
console.log('Utgivarförhandsvisning via jQuery/Select2: OK');

// Only http(s) URLs become links in the publisher preview.
assert.match(
  require('node:fs').readFileSync(require('node:path').join(__dirname, '../../assets/js/actor-quick-create.js'), 'utf8'),
  /\^https\?:\\\/\\\/\/i\.test\(option\.dataset\.url\)/
);
