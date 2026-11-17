(function () {
  'use strict';

  // A table of contents in the column to the left of a registry page (0.6.0): the headings (h2) of the main column, listed
  // when there are at least two, kept in view while the page scrolls (page-toc.css), with the heading being read marked.
  // The list is built from the page itself, so no page has to keep one by hand. Without this script the list stays hidden.
  var OFFSET = 96;
  var ARRIVAL_MS = 2000;

  function slug(text, taken) {
    var base = 'section-' + (text || '').toLowerCase().trim().replace(/[^a-z0-9À-ɏ]+/g, '-').replace(/^-+|-+$/g, '');
    if (base === 'section-') base = 'section';
    var id = base;
    for (var n = 2; taken(id); n++) id = base + '-' + n;
    return id;
  }

  // The heading being read: the last one whose top has passed the offset, or the first before any has. At the bottom of
  // the page the last heading, which can never scroll up to the offset.
  function currentIndex(tops, offset, atBottom) {
    if (atBottom && tops.length) return tops.length - 1;
    var current = 0;
    for (var i = 0; i < tops.length; i++) if (tops[i] <= offset) current = i;
    return current;
  }

  function setup(nav) {
    var main = document.querySelector('[role="main"]');
    var list = nav.querySelector('[data-page-toc-list]');
    if (!main || !list) return;
    var headings = Array.prototype.filter.call(main.querySelectorAll('h2'), function (heading) {
      return heading.offsetParent !== null && (heading.textContent || '').trim();
    });
    if (headings.length < 2) return;
    var links = headings.map(function (heading) {
      if (!heading.id) heading.id = slug(heading.textContent, function (id) { return !!document.getElementById(id); });
      var item = document.createElement('li');
      var link = document.createElement('a');
      link.href = '#' + heading.id;
      link.textContent = heading.textContent.trim();
      item.appendChild(link);
      list.appendChild(item);
      return link;
    });
    links.forEach(function (link, i) {
      link.addEventListener('click', function () { clicked = i; arrived = false; clickedAt = Date.now(); window.requestAnimationFrame(mark); });
    });
    nav.hidden = false;
    var shown = -1;
    var clicked = -1;
    var arrived = false;
    var clickedAt = 0;
    function atBottom() {
      var root = document.documentElement;
      return !!root && root.scrollHeight > window.innerHeight && window.innerHeight + window.scrollY >= root.scrollHeight - 2;
    }
    function mark() {
      var tops = headings.map(function (heading) { return heading.getBoundingClientRect().top; });
      var index = currentIndex(tops, OFFSET, atBottom());
      // A heading chosen in the list stays marked while it is on screen, also when the page cannot scroll it to the top. A
      // smooth scroll (the theme may ask for one) takes a moment to bring it there: until it has arrived, for a short while,
      // it is marked although it is still off screen.
      if (clicked >= 0) {
        var onScreen = tops[clicked] >= 0 && tops[clicked] < window.innerHeight;
        if (onScreen) arrived = true;
        if (onScreen || (!arrived && Date.now() - clickedAt < ARRIVAL_MS)) index = clicked;
        else clicked = -1;
      }
      if (index === shown) return;
      shown = index;
      links.forEach(function (link, i) {
        if (i === index) { link.classList.add('active'); link.setAttribute('aria-current', 'location'); }
        else { link.classList.remove('active'); link.removeAttribute('aria-current'); }
      });
    }
    var waiting = false;
    window.addEventListener('scroll', function () {
      if (waiting) return;
      waiting = true;
      window.requestAnimationFrame(function () { waiting = false; mark(); });
    }, { passive: true });
    window.addEventListener('resize', mark);
    mark();
  }

  function start() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-page-toc]'), setup);
  }
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { slug: slug, currentIndex: currentIndex };
})();
