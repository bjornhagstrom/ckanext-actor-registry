(function () {
  'use strict';

  function start() {
    document.querySelectorAll('[data-actors-widget]').forEach(function (root) {
      if (root.dataset.ready === 'true') return;
      root.dataset.ready = 'true';
      var i18n = {
        edit: root.dataset.i18nEdit || 'Edit',
        kindLabel: root.dataset.i18nKindLabel || 'Kind',
        kindPerson: root.dataset.i18nKindPerson || 'Person',
        kindOrganization: root.dataset.i18nKindOrganization || 'Organization',
        identifierLabel: root.dataset.i18nIdentifierLabel || 'Identifier',
        descriptionLabel: root.dataset.i18nDescriptionLabel || 'Description',
        urlLabel: root.dataset.i18nUrlLabel || 'URL',
        createTitle: root.dataset.i18nCreateTitle || 'New publisher',
        editTitle: root.dataset.i18nEditTitle || 'Edit publisher',
        saveCreate: root.dataset.i18nSaveCreate || 'Save and select',
        saveEdit: root.dataset.i18nSaveEdit || 'Save changes',
        nameRequired: root.dataset.i18nNameRequired || 'Name is required.',
        sessionExpired: root.dataset.i18nSessionExpired || 'Your session has expired. Open a new tab, log in again and try again.',
        unexpectedResponse: root.dataset.i18nUnexpectedResponse || 'The server responded unexpectedly. Reload the page and try again.',
        saveFailed: root.dataset.i18nSaveFailed || 'The publisher could not be saved.'
      };
      var select = root.querySelector('select[name="publisher_actor_id"]');
      var preview = root.querySelector('[data-actors-preview]');
      var panel = root.querySelector('[data-actors-panel]');
      var panelTitle = root.querySelector('[data-actors-panel-title]');
      var toggle = root.querySelector('[data-actors-toggle]');
      var cancel = root.querySelector('[data-actors-cancel]');
      var save = root.querySelector('[data-actors-save]');
      var form = root.querySelector('[data-actors-form]');
      var error = root.querySelector('[data-actors-error]');
      if (!select || !preview) return;

      function render() {
        preview.replaceChildren();
        var option = select.options[select.selectedIndex];
        if (!option || !option.value) return;
        var card = document.createElement('div');
        card.className = 'alert alert-light border mb-2';
        var headingRow = document.createElement('div');
        headingRow.className = 'd-flex justify-content-between align-items-start';
        var heading = document.createElement('strong');
        heading.textContent = option.textContent.trim();
        headingRow.appendChild(heading);
        if (toggle) {
          var editBtn = document.createElement('button');
          editBtn.type = 'button';
          editBtn.className = 'btn btn-link btn-sm p-0 ml-2';
          editBtn.textContent = i18n.edit;
          editBtn.addEventListener('click', function () { openForEdit(option); });
          headingRow.appendChild(editBtn);
        }
        card.appendChild(headingRow);
        [[i18n.kindLabel, option.dataset.kind === 'person' ? i18n.kindPerson : i18n.kindOrganization],
         [i18n.identifierLabel, option.dataset.identifier],
         [i18n.descriptionLabel, option.dataset.description]].forEach(function (pair) {
          if (pair[1]) {
            var line = document.createElement('div');
            line.textContent = pair[0] + ': ' + pair[1];
            card.appendChild(line);
          }
        });
        if (option.dataset.url) {
          var line = document.createElement('div'), link = document.createElement('a');
          line.textContent = i18n.urlLabel + ': ';
          // Stored values are not trusted to be http(s): only those become links.
          if (/^https?:\/\//i.test(option.dataset.url)) {
            link.href = option.dataset.url;
            link.textContent = option.dataset.url;
            line.appendChild(link);
          } else {
            line.appendChild(document.createTextNode(option.dataset.url));
          }
          card.appendChild(line);
        }
        preview.appendChild(card);
      }

      select.addEventListener('change', render);
      if (window.jQuery) {
        window.jQuery(select).on('change.actorRegistryPreview select2:select.actorRegistryPreview select2:unselect.actorRegistryPreview', render);
      }
      select.addEventListener('input', render);
      render();
      if (!toggle || !panel || !form || !save) return;

      function resetToCreateMode() {
        delete panel.dataset.editingId;
        if (panelTitle) panelTitle.textContent = i18n.createTitle;
        save.textContent = i18n.saveCreate;
        form.querySelectorAll('[data-field]').forEach(function (field) { field.value = ''; });
      }

      function openForEdit(option) {
        error.hidden = true;
        panel.dataset.editingId = option.value;
        if (panelTitle) panelTitle.textContent = i18n.editTitle;
        save.textContent = i18n.saveEdit;
        form.querySelector('[data-field="name"]').value = option.textContent.trim();
        form.querySelector('[data-field="actor_kind"]').value = option.dataset.kind || 'organization';
        form.querySelector('[data-field="identifier"]').value = option.dataset.identifier || '';
        form.querySelector('[data-field="identifier_scheme"]').value = option.dataset.identifierScheme || '';
        form.querySelector('[data-field="url"]').value = option.dataset.url || '';
        panel.hidden = false;
        toggle.hidden = true;
        form.querySelector('[data-field="name"]').focus();
      }

      // Note: the quick-create panel's own fields use data-field (not name)
      // so they are never picked up by the browser when the *outer* CKAN
      // dataset form is submitted natively. Using name="name"/"identifier"/
      // "url" here previously collided with the dataset form's own fields
      // that share those exact names, corrupting the dataset form submission
      // (the server received a list instead of a single value). See
      // TASKLISTA_SKELLEFTEA.md, 2026-09-05.
      toggle.addEventListener('click', function () {
        resetToCreateMode();
        panel.hidden = false;
        toggle.hidden = true;
        form.querySelector('[data-field="name"]').focus();
      });
      cancel.addEventListener('click', function () {
        resetToCreateMode();
        panel.hidden = true;
        toggle.hidden = false;
        error.hidden = true;
      });
      save.addEventListener('click', function () {
        var name = form.querySelector('[data-field="name"]');
        error.hidden = true;
        if (!name.value.trim()) {
          error.textContent = i18n.nameRequired;
          error.hidden = false;
          name.focus();
          return;
        }
        save.disabled = true;
        var payload = new FormData();
        form.querySelectorAll('[data-field]').forEach(function (field) { payload.append(field.dataset.field, field.value); });
        var csrf = form.querySelector('input[name="_csrf_token"]');
        if (csrf) payload.append('_csrf_token', csrf.value);
        var editingId = panel.dataset.editingId || '';
        var endpoint = editingId
          ? root.dataset.editEndpointTemplate.replace('__ID__', encodeURIComponent(editingId))
          : root.dataset.endpoint;
        fetch(endpoint, {
          method: 'POST',
          credentials: 'include',
          headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
          body: payload
        }).then(function (response) {
          return response.text().then(function (raw) {
            if (response.redirected || response.url.indexOf('/user/login') !== -1) throw new Error(i18n.sessionExpired);
            var body;
            try { body = JSON.parse(raw); }
            catch (parseError) { throw new Error(i18n.unexpectedResponse); }
            if (!response.ok || !body.success) throw new Error(body.error || i18n.saveFailed);
            return body.actor;
          });
        }).then(function (actor) {
          if (editingId) {
            var existing = select.querySelector('option[value="' + CSS.escape(editingId) + '"]');
            if (existing) {
              existing.textContent = actor.name;
              existing.dataset.kind = actor.kind || '';
              existing.dataset.identifier = actor.identifier || '';
              existing.dataset.identifierScheme = actor.identifier_scheme || '';
              existing.dataset.url = actor.url || '';
              existing.dataset.description = actor.description || '';
            }
          } else {
            var option = new Option(actor.name, actor.id, true, true);
            option.dataset.kind = actor.kind || '';
            option.dataset.identifier = actor.identifier || '';
            option.dataset.identifierScheme = actor.identifier_scheme || '';
            option.dataset.url = actor.url || '';
            option.dataset.description = actor.description || '';
            select.appendChild(option);
          }
          if (window.jQuery) window.jQuery(select).trigger('change');
          else select.dispatchEvent(new Event('change', {bubbles: true}));
          resetToCreateMode();
          panel.hidden = true;
          toggle.hidden = false;
        }).catch(function (problem) {
          error.textContent = problem.message;
          error.hidden = false;
        }).finally(function () { save.disabled = false; });
      });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
}());
