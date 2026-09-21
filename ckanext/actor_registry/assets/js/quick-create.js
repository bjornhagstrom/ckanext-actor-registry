(function () {
  'use strict';

  function start() {
    document.querySelectorAll('[data-contactpoints-widget]').forEach(function (root) {
      if (root.dataset.ready === 'true') return;
      root.dataset.ready = 'true';

      var i18n = {
        edit: root.dataset.i18nEdit || 'Edit',
        emailLabel: root.dataset.i18nEmailLabel || 'Email',
        phoneLabel: root.dataset.i18nPhoneLabel || 'Phone',
        urlLabel: root.dataset.i18nUrlLabel || 'URL',
        selectHint: root.dataset.i18nSelectHint || 'Select a contact point to see its details here.',
        createTitle: root.dataset.i18nCreateTitle || 'New contact point',
        editTitle: root.dataset.i18nEditTitle || 'Edit contact point',
        saveCreate: root.dataset.i18nSaveCreate || 'Save and select',
        saveEdit: root.dataset.i18nSaveEdit || 'Save changes',
        nameRequired: root.dataset.i18nNameRequired || 'Name or role is required.',
        sessionExpired: root.dataset.i18nSessionExpired || 'Your session has expired. Open a new tab, log in again and try again.',
        unexpectedResponse: root.dataset.i18nUnexpectedResponse || 'The server responded unexpectedly. Reload the page and try again.',
        saveFailed: root.dataset.i18nSaveFailed || 'The contact point could not be saved.'
      };

      var select = root.querySelector('select[name="contact_point_ids"]');
      var preview = root.querySelector('[data-contactpoints-preview]');
      var panel = root.querySelector('[data-contactpoints-panel]');
      var panelTitle = root.querySelector('[data-contactpoints-panel-title]');
      var toggle = root.querySelector('[data-contactpoints-toggle]');
      var cancel = root.querySelector('[data-contactpoints-cancel]');
      var save = root.querySelector('[data-contactpoints-save]');
      var form = root.querySelector('[data-contactpoints-form]');
      var error = root.querySelector('[data-contactpoints-error]');
      if (!select || !preview) return;

      function row(label, value, href) {
        if (!value) return '';
        var safe = document.createElement('div');
        var strong = document.createElement('strong');
        strong.textContent = label + ': ';
        safe.appendChild(strong);
        // Only web, mail and phone links are made clickable; a stored value with any
        // other scheme (e.g. javascript:) is shown as plain text.
        if (href && /^(https?:|mailto:|tel:)/i.test(href)) {
          var link = document.createElement('a');
          link.href = href;
          link.textContent = value;
          safe.appendChild(link);
        } else {
          safe.appendChild(document.createTextNode(value));
        }
        return safe;
      }

      function render() {
        preview.replaceChildren();
        Array.from(select.selectedOptions).forEach(function (option) {
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
          var email = option.dataset.email || '';
          var phone = option.dataset.phone || '';
          var url = option.dataset.url || '';
          [row(i18n.emailLabel, email, email ? 'mailto:' + email : ''),
           row(i18n.phoneLabel, phone, phone ? 'tel:' + phone.replace(/[^0-9+]/g, '') : ''),
           row(i18n.urlLabel, url, url)].forEach(function (item) { if (item) card.appendChild(item); });
          preview.appendChild(card);
        });
        if (!select.selectedOptions.length) {
          var hint = document.createElement('p');
          hint.className = 'help-block';
          hint.textContent = i18n.selectHint;
          preview.appendChild(hint);
        }
      }

      select.addEventListener('change', render);
      // CKAN's autocomplete widget uses jQuery/Select2 and may trigger a
      // jQuery change without dispatching a native DOM event. Listen to both
      // event systems so the preview is updated for mouse and keyboard use.
      if (window.jQuery) {
        window.jQuery(select).on(
          'change.actorRegistryPreview select2:select.actorRegistryPreview select2:unselect.actorRegistryPreview',
          render
        );
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
        form.querySelector('[data-field="email"]').value = option.dataset.email || '';
        form.querySelector('[data-field="phone"]').value = option.dataset.phone || '';
        form.querySelector('[data-field="url"]').value = option.dataset.url || '';
        var actorField = form.querySelector('[data-field="actor_id"]');
        if (actorField) actorField.value = option.dataset.actorId || '';
        panel.hidden = false;
        toggle.hidden = true;
        form.querySelector('[data-field="name"]').focus();
      }

      // Note: the quick-create panel's own fields use data-field (not name)
      // so they are never picked up by the browser when the *outer* CKAN
      // dataset form is submitted natively. Using name="name"/"url" here
      // previously collided with the dataset form's own fields that share
      // those exact names, corrupting the dataset form submission (the
      // server received a list instead of a single value). See
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
            if (response.redirected || response.url.indexOf('/user/login') !== -1) {
              throw new Error(i18n.sessionExpired);
            }
            var body;
            try { body = JSON.parse(raw); }
            catch (parseError) { throw new Error(i18n.unexpectedResponse); }
            if (!response.ok || !body.success) throw new Error(body.error || i18n.saveFailed);
            return body.contact_point;
          });
        }).then(function (contact) {
          if (editingId) {
            var existing = select.querySelector('option[value="' + CSS.escape(editingId) + '"]');
            if (existing) {
              existing.textContent = contact.name;
              existing.dataset.email = contact.email || '';
              existing.dataset.phone = contact.phone || '';
              existing.dataset.url = contact.url || '';
              existing.dataset.actorId = contact.actor_id || '';
            }
          } else {
            var option = new Option(contact.name, contact.id, true, true);
            option.dataset.email = contact.email || '';
            option.dataset.phone = contact.phone || '';
            option.dataset.url = contact.url || '';
            option.dataset.actorId = contact.actor_id || '';
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
