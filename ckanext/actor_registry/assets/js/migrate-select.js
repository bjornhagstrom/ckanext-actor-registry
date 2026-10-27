(function () {
  'use strict';

  // A large group on the contact migration page: a table, ticked = included, with one box in the heading for all or none and headings that sort
  // the rows. The unticked datasets
  // are posted as exclude_ids when the form is sent. Without this script the page shows the boxes that leave datasets out.
  // The button says how many datasets it acts on, and cannot be pressed for none: an editor should see what a click will do.
  function countButton(form, counter) {
    var button = form.querySelector('[data-apply-button]');
    if (!button) return function () {};
    return function () {
      var count = counter();
      var text = count === 0 ? button.getAttribute('data-i18n-none') :
        (count === 1 ? button.getAttribute('data-i18n-one') : button.getAttribute('data-i18n-many'));
      if (text) button.textContent = text.replace('{count}', count);
      button.disabled = count === 0;
    };
  }

  // The box in the heading (ticked for all, empty for none, in between for some) and the headings that sort the rows, for any table of datasets.
  function enableTable(table, boxes, changed) {
    var master = table.querySelector('[data-include-master]');
    function refresh() {
      var included = boxes.filter(function (box) { return box.checked; }).length;
      if (master) {
        master.checked = included === boxes.length;
        master.indeterminate = included > 0 && included < boxes.length;
      }
    }
    boxes.forEach(function (box) { box.addEventListener('change', function () { refresh(); changed(); }); });
    if (master) master.addEventListener('change', function () {
      boxes.forEach(function (box) { box.checked = master.checked; });
      refresh();
      changed();
    });
    // The headings sort the rows; a second click on the same heading reverses the order.
    var body = table.querySelector('tbody');
    var sorted = { key: null, down: false };
    Array.prototype.forEach.call(table.querySelectorAll('[data-sort]'), function (heading) {
      heading.addEventListener('click', function () {
        var key = heading.getAttribute('data-sort');
        sorted = { key: key, down: sorted.key === key && !sorted.down };
        var rows = Array.prototype.slice.call(body.querySelectorAll('tr')).sort(compareBy(key));
        if (sorted.down) rows.reverse();
        rows.forEach(function (row) { body.appendChild(row); });
        Array.prototype.forEach.call(table.querySelectorAll('[data-sort]'), function (other) {
          var on = other === heading;
          other.parentNode.setAttribute('aria-sort', on ? (sorted.down ? 'descending' : 'ascending') : 'none');
          var mark = other.querySelector('[data-sort-mark]');
          if (mark) mark.textContent = on ? (sorted.down ? ' \u25BE' : ' \u25B4') : '';
        });
      });
    });
    refresh();
  }

  function setupSmall(form) {
    var table = form.querySelector('[data-table-list]');
    var boxes = Array.prototype.slice.call(form.querySelectorAll('input[name="dataset_ids"]'));
    if (!boxes.length) return;
    var update = countButton(form, function () { return boxes.filter(function (box) { return box.checked; }).length; });
    if (table) enableTable(table, boxes, update);
    else boxes.forEach(function (box) { box.addEventListener('change', update); });
    update();
  }

  // The rows in the order of a heading: text compared as Swedish text with numbers as numbers, an empty cell last.
  function compareBy(key) {
    var collator = typeof Intl !== 'undefined' && Intl.Collator ? new Intl.Collator('sv', { numeric: true, sensitivity: 'base' }) : null;
    return function (a, b) {
      var x = a.getAttribute('data-' + key) || '', y = b.getAttribute('data-' + key) || '';
      if (!x && y) return 1;
      if (x && !y) return -1;
      return collator ? collator.compare(x, y) : (x < y ? -1 : (x > y ? 1 : 0));
    };
  }

  function setup(form) {
    var details = form.querySelector('[data-large-details]');
    if (!details) { setupSmall(form); return; }
    var plain = details.querySelector('[data-exclude-list]');
    var enhanced = details.querySelector('[data-include-list]');
    var summary = form.querySelector('[data-large-group]');
    var help = form.querySelector('[data-large-help]');
    var boxes = Array.prototype.slice.call(enhanced.querySelectorAll('[data-include-box]'));

    Array.prototype.forEach.call(plain.querySelectorAll('input'), function (input) { input.disabled = true; });
    plain.hidden = true;
    enhanced.hidden = false;
    if (help && help.getAttribute('data-i18n-js')) help.textContent = help.getAttribute('data-i18n-js');

    var updateButton = countButton(form, function () { return boxes.filter(function (box) { return box.checked; }).length; });
    function update() {
      var included = boxes.filter(function (box) { return box.checked; }).length;
      updateButton();
      if (!summary) return;
      var template = details.getAttribute('data-i18n-count') || '{included} of {total} datasets are included.';
      summary.textContent = included ? template.replace('{included}', included).replace('{total}', boxes.length)
        : (details.getAttribute('data-i18n-none') || 'No dataset is included.');
    }
    enableTable(enhanced, boxes, update);

    form.addEventListener('submit', function () {
      Array.prototype.forEach.call(form.querySelectorAll('input[data-excluded]'), function (old) { old.parentNode.removeChild(old); });
      boxes.forEach(function (box) {
        if (box.checked) return;
        var hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'exclude_ids';
        hidden.value = box.value;
        hidden.setAttribute('data-excluded', '');
        form.appendChild(hidden);
      });
    });
    update();
  }

  function start() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-candidate] form'), setup);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { compareBy: compareBy };
})();
