(function () {
  'use strict';

  // The To do list (0.6.0). Without this script the boxes, both bars and the Save buttons still work; only the helps below
  // are missing.
  // - "Select all" in the bars above and below the list, kept in step with the row boxes, and each choice in one bar kept
  //   in step with the same choice in the other, so the bar at the bottom of a long list does what the one at the top shows.
  // - Save saves everything: each row's own choices, and the bar's choices on the ticked rows. Its button says how many
  //   datasets that is, and cannot be pressed for none; with rows ticked and nothing chosen in the bar it says so.
  // - A ticked row is shaded, and a row with a choice that is not saved is marked "Not saved".
  // - Leaving the page with anything ticked or chosen and not saved asks first, with what would be lost.
  // - A save comes back where the page was, not at its top, and its messages float in view when the list's top is not.
  // - "Create new…" in each list opens a small dialog that saves a new publisher or contact point at once (the same
  //   quick create as the dataset form), adds it to every list of its kind and chooses it in the list it came from.
  var NEW = '__new__';
  var SCROLL_KEY = 'actor-registry-todo-scroll';
  var SCROLL_FRESH_MS = 60000;  // a save comes back in seconds; an older position is from a save that never came back

  function list(root, selector) { return Array.prototype.slice.call(root.querySelectorAll(selector)); }

  // A row's dataset id for a row's own choice, 'bar' for the bars above and below the list.
  function where(select) {
    var row = (select.name || '').match(/^(?:publisher|contact_point)_for_(.+)$/);
    if (row) return row[1];
    return select.hasAttribute('data-assign-choice') ? 'bar' : null;
  }

  function chosen(select) { return !!select.value && select.value !== NEW; }

  function plural(form, name, count) {
    var text = form.getAttribute('data-i18n-' + name + (count === 1 ? '-one' : '-many')) || '';
    return text.replace('{count}', count);
  }

  function storage() {
    try { return window.sessionStorage || null; } catch (error) { return null; }
  }

  // Back where the page was before a save, and its messages in view.
  function restoreScroll() {
    var store = storage();
    var saved = null;
    try { saved = store && store.getItem(SCROLL_KEY); if (saved !== null) store.removeItem(SCROLL_KEY); } catch (error) { saved = null; }
    if (saved === null || typeof window.scrollTo !== 'function') return;
    var position = JSON.parse(saved);
    if (!position || position.path !== window.location.pathname || !(Date.now() - position.at < SCROLL_FRESH_MS)) return;
    // After the browser's own jump to #todo-list (the place without this script), which comes when the page is parsed.
    if (document.readyState !== 'complete' && typeof window.addEventListener === 'function') {
      window.addEventListener('load', function () { backTo(position.y); });
    } else {
      backTo(position.y);
    }
  }

  function backTo(y) {
    // At once: a theme's smooth scrolling (scroll-behavior) would still be on its way when the messages are measured.
    var root = document.documentElement;
    var end = Math.max(0, Math.min(y, root ? root.scrollHeight - window.innerHeight : y));
    window.scrollTo({ top: end, left: 0, behavior: 'instant' });
    var messages = document.querySelector('[data-todo-messages]');
    if (!messages || !messages.children.length || !messages.getBoundingClientRect) return;
    // Where the messages are on the page, against where it ends up, not where the browser happens to be yet.
    var box = messages.getBoundingClientRect();
    var top = box.top + (window.scrollY || 0);
    var bottom = box.bottom + (window.scrollY || 0);
    if (bottom > end && top < end + window.innerHeight) return;
    messages.classList.add('todo-messages-float');
    var drop = function () { messages.classList.remove('todo-messages-float'); };
    setTimeout(drop, 8000);
    messages.addEventListener('click', drop);
  }

  function setup(form) {
    var boxes = list(form, '[data-assign-dataset]');
    var alls = list(form, '[data-assign-all]');
    var choices = list(form, '[data-assign-choice]');
    var saves = list(form, '[data-assign-save]');
    var leaving = false;
    if (boxes.length) list(form, '[data-assign-all-wrap]').forEach(function (wrap) { wrap.hidden = false; });

    function tickedIds() {
      return boxes.filter(function (box) { return box.checked; }).map(function (box) { return box.value; });
    }

    function rowsWithChoice() {
      var rows = {};
      list(form, 'select').forEach(function (select) {
        var place = where(select);
        if (place && place !== 'bar' && chosen(select)) rows[place] = true;
      });
      return rows;
    }

    function barChosen() { return choices.some(chosen); }

    // The datasets a Save would change: the rows with a choice of their own, and the ticked rows when the bar has one.
    function toSave() {
      var ids = rowsWithChoice();
      if (barChosen()) tickedIds().forEach(function (id) { ids[id] = true; });
      return Object.keys(ids).length;
    }

    function refresh() {
      var count = tickedIds().length;
      alls.forEach(function (all) {
        all.checked = count > 0 && count === boxes.length;
        all.indeterminate = count > 0 && count < boxes.length;
      });
      var saving = toSave();
      saves.forEach(function (button) {
        var text = saving ? (button.getAttribute(saving === 1 ? 'data-i18n-one' : 'data-i18n-many') || '').replace('{count}', saving)
          : button.getAttribute(count ? 'data-i18n-pick' : 'data-i18n-none');
        if (text) button.textContent = text;
        button.disabled = saving === 0;
      });
      var withChoice = rowsWithChoice();
      list(form, '[data-assign-row]').forEach(function (row) {
        var id = row.getAttribute('data-assign-row');
        var box = row.querySelector('[data-assign-dataset]');
        if (box && box.checked) row.classList.add('table-active'); else row.classList.remove('table-active');
        var unsaved = !!withChoice[id];
        if (unsaved) row.classList.add('table-info'); else row.classList.remove('table-info');
        var badge = row.querySelector('[data-unsaved-badge]');
        if (badge) badge.hidden = !unsaved;
      });
    }

    function unsaved() {
      return { selected: tickedIds().length, chosen: Object.keys(rowsWithChoice()).length };
    }

    // True when the visitor may leave: nothing unsaved, or they said so.
    function mayLeave() {
      var state = unsaved();
      if (!state.selected && !state.chosen) return true;
      var text = form.getAttribute('data-i18n-leave');
      if (!text) return true;
      var details = [];
      if (state.chosen) details.push(plural(form, 'chosen', state.chosen));
      if (state.selected) details.push(plural(form, 'selected', state.selected));
      var ok = window.confirm(text.replace('{details}', details.join(', ')));
      if (ok) leaving = true;
      return ok;
    }

    alls.forEach(function (all) {
      all.addEventListener('change', function () {
        boxes.forEach(function (box) { box.checked = all.checked; });
        refresh();
      });
    });
    boxes.forEach(function (box) { box.addEventListener('change', refresh); });
    choices.forEach(function (choice) {
      choice.addEventListener('change', function () {
        if (choice.value === NEW) return;
        choices.forEach(function (other) {
          if (other.getAttribute('data-assign-choice') !== choice.getAttribute('data-assign-choice')) return;
          other.value = choice.value;
          other.assignPrevious = choice.value;  // what "Cancel" in "Create new…" goes back to
        });
        refresh();
      });
    });
    list(form, 'select').forEach(function (select) {
      if (!select.hasAttribute('data-assign-choice')) select.addEventListener('change', refresh);
    });

    // A save leaves nothing behind, and comes back where the page was.
    form.addEventListener('submit', function () {
      leaving = true;
      var store = storage();
      try {
        if (store) store.setItem(SCROLL_KEY, JSON.stringify({ path: window.location.pathname, y: window.scrollY || 0, at: Date.now() }));
      } catch (error) { /* the page then opens at the list instead */ }
    });

    // Leaving by a link or another form of the page asks with the numbers; closing the tab, Back or a typed address
    // get the browser's own question, which cannot carry a text of our own.
    if (typeof document.addEventListener === 'function') {
      document.addEventListener('click', function (event) {
        // A click that opens a new tab or window (Ctrl, Cmd, Shift, the middle button) leaves nothing behind.
        if (event.defaultPrevented || event.button > 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        var link = event.target && event.target.closest ? event.target.closest('a[href]') : null;
        if (!link || leaving || link.target === '_blank') return;
        var href = link.getAttribute('href') || '';
        if (href.charAt(0) === '#') return;
        if (!mayLeave()) event.preventDefault();
      });
      document.addEventListener('submit', function (event) {
        if (event.target === form || leaving) return;
        if (!mayLeave()) event.preventDefault();
      });
    }
    if (typeof window.addEventListener === 'function') {
      window.addEventListener('beforeunload', function (event) {
        if (leaving) return;
        var state = unsaved();
        if (state.selected || state.chosen) { event.preventDefault(); event.returnValue = ''; }
      });
    }

    setupCreate(form, refresh);
    refresh();
    return { refresh: refresh, unsaved: unsaved, mayLeave: mayLeave, toSave: toSave };
  }

  // "Create new…": an option last in each list, and a dialog per kind.
  function setupCreate(form, refresh) {
    var label = form.getAttribute('data-i18n-create-new');
    if (!label || typeof document.querySelector !== 'function') return;
    var dialogs = {};
    list(document, '[data-create-dialog]').forEach(function (dialog) {
      if (typeof dialog.showModal === 'function') dialogs[dialog.getAttribute('data-create-dialog')] = dialog;
    });
    var selects = list(form, 'select[data-assign-kind]').filter(function (select) {
      return dialogs[select.getAttribute('data-assign-kind')];
    });
    selects.forEach(function (select) {
      var option = document.createElement('option');
      option.value = NEW;
      option.textContent = label;
      select.appendChild(option);
      select.assignPrevious = select.value;
      select.addEventListener('change', function () {
        if (select.value === NEW) open(dialogs[select.getAttribute('data-assign-kind')], select, select.assignPrevious);
        else select.assignPrevious = select.value;
      });
    });

    var current = null;
    function open(dialog, select, previous) {
      current = { dialog: dialog, select: select, previous: previous };
      list(dialog, '[data-field]').forEach(function (field) { if (field.tagName !== 'SELECT') field.value = ''; });
      dialog.querySelector('[data-create-error]').hidden = true;
      dialog.querySelector('[data-create-save]').disabled = false;
      dialog.showModal();
      var name = dialog.querySelector('[data-field="name"]');
      if (name) name.focus();
    }
    function close(chosenId) {
      if (!current) return;
      var select = current.select;
      var previous = current.previous;
      current.dialog.close();
      current = null;
      select.value = chosenId || previous || '';
      select.dispatchEvent(new Event('change'));
      select.focus();
    }

    Object.keys(dialogs).forEach(function (kind) {
      var dialog = dialogs[kind];
      dialog.querySelector('[data-create-cancel]').addEventListener('click', function () { close(''); });
      dialog.addEventListener('cancel', function (event) { event.preventDefault(); close(''); });
      var save = dialog.querySelector('[data-create-save]');
      save.addEventListener('click', function () {
        var error = dialog.querySelector('[data-create-error]');
        var name = dialog.querySelector('[data-field="name"]');
        if (!name.value.trim()) { name.focus(); return; }
        var payload = new FormData();
        list(dialog, '[data-field]').forEach(function (field) { payload.append(field.getAttribute('data-field'), field.value); });
        var csrf = dialog.querySelector('input[name="_csrf_token"]');
        if (csrf) payload.append('_csrf_token', csrf.value);
        save.disabled = true;
        // The answer belongs to this opening of the dialog: cancelled meanwhile, or opened again
        // from another list, it only adds the new record to the lists and chooses nothing.
        var context = current;
        fetch(dialog.getAttribute('data-endpoint'), {
          method: 'POST', credentials: 'include', body: payload,
          headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function (response) {
          return response.json().catch(function () { return {}; }).then(function (body) {
            if (!response.ok || !body.success) throw new Error(body.error || dialog.getAttribute('data-i18n-failed'));
            return body.actor || body.contact_point;
          });
        }).then(function (item) {
          var text = (item.display_name || item.name) + (kind === 'contact_point' && item.email ? ' (' + item.email + ')' : '');
          list(form, 'select[data-assign-kind="' + kind + '"]').forEach(function (select) {
            var option = document.createElement('option');
            option.value = item.id;
            option.textContent = text;
            var last = select.querySelector('option[value="' + NEW + '"]');
            select.insertBefore(option, last);
          });
          if (current === context) close(item.id);
        }).catch(function (problem) {
          if (current !== context) return;
          error.textContent = problem.message || dialog.getAttribute('data-i18n-failed');
          error.hidden = false;
        }).finally(function () { if (current === context || !current) save.disabled = false; });
      });
    });
  }

  function start() {
    list(document, '[data-assign-links]').forEach(setup);
    restoreScroll();
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { setup: setup, restoreScroll: restoreScroll };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
