(function () {
  'use strict';

  // The filters of the To do list (0.6.0): a tag or an organisation applies as soon as it is chosen, and the Filter button
  // is not needed: the search field applies with Enter. Without this script the button applies them all.
  // The page's own question about unsaved choices (assign-links.js) still comes first: if the visitor stays, the list
  // goes back to "Add …".
  function setup(form) {
    var selects = Array.prototype.slice.call(form.querySelectorAll('select[data-filter-auto]'));
    var button = form.querySelector('[data-filter-button]');
    if (button) button.hidden = true;
    // A list left at "Add …" is not sent, so the address gets no empty tag= or org=.
    form.addEventListener('submit', function () {
      var empty = selects.filter(function (select) { return !select.value; });
      empty.forEach(function (select) { select.disabled = true; });
      setTimeout(function () { empty.forEach(function (select) { select.disabled = false; }); }, 0);
    });
    selects.forEach(function (select) {
      select.addEventListener('change', function () {
        if (!select.value) return;
        var stayed = function (event) {
          form.removeEventListener('submit', stayed);
          setTimeout(function () { if (event.defaultPrevented) select.value = ''; }, 0);
        };
        form.addEventListener('submit', stayed);
        if (typeof form.requestSubmit === 'function') form.requestSubmit();
        else { form.removeEventListener('submit', stayed); form.submit(); }
      });
    });
  }

  function start() {
    Array.prototype.slice.call(document.querySelectorAll('[data-todo-filters]')).forEach(setup);
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { setup: setup };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
