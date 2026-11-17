'use strict';

// The table of contents to the left of a registry page: a list of the main column's headings, with the one being read marked.

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', '..', 'assets', 'js', 'page-toc.js'), 'utf8');

function element(tag, extra) {
  const listeners = {};
  const classes = new Set();
  return Object.assign({
    tag, children: [], attrs: {}, id: '', textContent: '', offsetParent: {},
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) },
    setAttribute(name, value) { this.attrs[name] = value; },
    removeAttribute(name) { delete this.attrs[name]; },
    appendChild(child) { this.children.push(child); },
    addEventListener(name, handler) { (listeners[name] = listeners[name] || []).push(handler); },
    fire(name) { (listeners[name] || []).forEach((handler) => handler()); }
  }, extra);
}

function page(headings) {
  const list = element('ul');
  const nav = element('nav', { hidden: true, querySelector: () => list });
  const main = element('div', { querySelectorAll: () => headings });
  const window = element('window', { requestAnimationFrame: (fn) => fn(), innerHeight: 800, scrollY: 0 });
  const document = {
    readyState: 'complete',
    documentElement: { scrollHeight: 3000 },
    querySelector: () => main,
    querySelectorAll: () => [nav],
    getElementById: (id) => headings.find((h) => h.id === id) || null,
    createElement: (tag) => element(tag)
  };
  const clock = { now: 0 };
  const sandbox = { document, window, module: { exports: {} }, Date: { now: () => clock.now } };
  vm.runInNewContext(source, sandbox);
  return { nav, list, window, document, clock, exported: sandbox.module.exports };
}

function heading(text, top, extra) {
  const h = element('h2', Object.assign({ textContent: text }, extra));
  h.top = top;
  h.getBoundingClientRect = () => ({ top: h.top });
  return h;
}

// Two headings or more: a list, ids given where missing (an existing id is kept), the first marked at the top of the page.
const hs = [heading('Overview', 200), heading('Skipped', 900, { id: 'skipped' }), heading('Close the migration', 1600),
  heading('Hidden', 2000, { offsetParent: null })];
const p = page(hs);
assert.strictEqual(p.nav.hidden, false);
const links = p.list.children.map((item) => item.children[0]);
assert.deepStrictEqual(links.map((a) => [a.textContent, a.href]),
  [['Overview', '#section-overview'], ['Skipped', '#skipped'], ['Close the migration', '#section-close-the-migration']]);
assert.strictEqual(links[0].attrs['aria-current'], 'location');
assert.ok(links[0].classList.contains('active'));

// Scrolling marks the heading that has passed the top.
hs.forEach((h) => { h.top -= 850; });
p.window.fire('scroll');
assert.strictEqual(links[0].attrs['aria-current'], undefined);
assert.strictEqual(links[1].attrs['aria-current'], 'location');
assert.ok(links[1].classList.contains('active') && !links[0].classList.contains('active'));

// One heading: no list.
const single = page([heading('Only', 100)]);
assert.strictEqual(single.nav.hidden, true);
assert.strictEqual(single.list.children.length, 0);

// The helpers: unique ids, letters beyond a-z kept, and the current heading.
const { slug, currentIndex } = p.exported;
const taken = new Set(['section-a']);
assert.strictEqual(slug('A', (id) => taken.has(id)), 'section-a-2');
assert.strictEqual(slug('Övrigt läge', () => false), 'section-övrigt-läge');
assert.strictEqual(slug('!!!', () => false), 'section');
assert.strictEqual(currentIndex([200, 900], 96), 0);
assert.strictEqual(currentIndex([-500, 50, 400], 96), 1);

// At the bottom of the page the last heading is the one being read.
assert.strictEqual(currentIndex([-900, -300, 400], 96, true), 2);
assert.strictEqual(currentIndex([], 96, true), 0);

// A click marks the chosen heading at once, also while a smooth scroll is still on its way to it, and keeps it marked while
// it is on screen though the page cannot bring it to the top; once it has left the screen the scroll position decides.
const ch = [heading('One', 200), heading('Two', 900), heading('Three', 1500), heading('Four', 2100)];
const c = page(ch);
const clinks = c.list.children.map((item) => item.children[0]);
const marked = () => clinks.findIndex((a) => a.attrs['aria-current'] === 'location');
clinks[2].fire('click');
assert.strictEqual(marked(), 2);                      // Three is still below the screen
c.clock.now = 300; ch.forEach((h) => { h.top -= 300; }); c.window.fire('scroll');
assert.strictEqual(marked(), 2);                      // on its way
c.clock.now = 600; ch.forEach((h) => { h.top -= 700; }); c.window.fire('scroll');
assert.strictEqual(marked(), 2);                      // arrived, at 500 px: on screen, not at the top
ch.forEach((h) => { h.top -= 600; }); c.window.fire('scroll');
assert.strictEqual(marked(), 2);                      // Three has passed the top on its own
ch.forEach((h) => { h.top += 1200; }); c.window.fire('scroll');
assert.strictEqual(marked(), 0);                      // scrolled back up past it: the position decides again
// A click whose scroll never arrives lets go after a while.
clinks[3].fire('click');
c.clock.now = 5000; c.window.fire('scroll');
assert.strictEqual(marked(), 0);

// At the bottom of the page the last heading is marked, though it cannot reach the top.
const bh = [heading('A', 200), heading('B', 900), heading('C', 1500)];
const b = page(bh);
const blinks = b.list.children.map((item) => item.children[0]);
bh.forEach((h) => { h.top -= 1000; });
b.window.scrollY = 2200; b.window.fire('scroll');
assert.strictEqual(blinks[2].attrs['aria-current'], 'location');
