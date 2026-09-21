# Translations

The interface is in English by default and comes with Swedish translations (`sv` and
`sv_SE`). This page explains how the translations work and how to change or add them.

## How it works

- **English is the source language.** Every user-facing string in the Python code and the
  templates is English text wrapped in gettext's `_()`. The English text itself is the
  translation key.
- **The catalogues** live in `ckanext/actor_registry/i18n/`: a template
  (`ckanext-actor-registry.pot`) and, per language, a `.po` file (the translations you edit)
  and a compiled `.mo` file (what CKAN loads). Both are committed, so no build step is needed
  to use the extension.
- **The plugin** registers them through CKAN's `ITranslation` (`i18n_locales`), so CKAN picks
  the catalogue that matches the visitor's language. `/sv/...` shows Swedish, `/en/...` English.
- **The site must offer the language.** CKAN core ships `sv` only. A site that wants `sv_SE`
  must list it in `ckan.locales_offered`; the extension ships a matching `sv_SE` catalogue, which
  is a plain copy of `sv` (a test fails if the two differ).
- **Field labels in your own Scheming schema are not translated by this extension.** Give your
  schema `label` and `help_text` entries per language (see the example schema in
  `ckanext/actor_registry/examples/`).

## Changing or adding a string

1. Write the English text in `_("...")` (Python) or `{{ _("...") }}` (templates). JavaScript
   strings are not translated in the browser: render them server-side as a `data-i18n-*`
   attribute and read that from the script (see `assets/js/actor-quick-create.js`).
2. Add the entry to `ckanext-actor-registry.pot` and to `sv/LC_MESSAGES/ckanext-actor-registry.po`
   with the Swedish text, and copy it to `sv_SE/LC_MESSAGES/ckanext-actor-registry.po`.
   To regenerate the template from the source, run from the repository root:

   ```console
   pybabel extract -F babel.cfg -o ckanext/actor_registry/i18n/ckanext-actor-registry.pot .
   ```

3. Compile the catalogues:

   ```console
   pybabel compile -d ckanext/actor_registry/i18n -D ckanext-actor-registry
   ```

4. Run the tests. `test_i18n_extraction.py` checks that extraction found every string in every
   template, and `test_help_texts_i18n.py` and the other translation tests check that messages
   and help texts appear in `en`, `sv` and `sv_SE`.

**Do not reword an English string casually.** The text is the key, so changing it orphans its
translations (this is why renaming "actor" to "publisher" in 0.2.0 was a breaking change for
anyone maintaining their own translations). When the English text has to change, change the
matching `msgid` in the `.pot` and in every `.po` in the same commit.

### A pitfall: silently missing strings

`pybabel extract` runs without CKAN, so it cannot parse CKAN's own template tags (`{% asset %}`,
`{% snippet %}`, `{% ckan_extends %}`), and Babel swallows the parse error: the whole template's
strings are dropped without a warning. `babel_ckan_tag_shims.py` (referenced from `babel.cfg`)
teaches it those tags, and `test_i18n_extraction.py` fails if a template's strings ever go
missing again. If you add a new custom tag, extend the shim.

## Adding a language

1. Create `ckanext/actor_registry/i18n/<locale>/LC_MESSAGES/ckanext-actor-registry.po` (for
   example with `pybabel init -i ckanext-actor-registry.pot -d ckanext/actor_registry/i18n -D
   ckanext-actor-registry -l <locale>`), translate it and compile it.
2. Add the locale to `i18n_locales()` in `plugin.py`.
3. Make sure the site offers the locale (`ckan.locales_offered`).
4. Add it to the translation tests.

Translations of the field-level help texts live in one place, the macro in
`templates/actor_registry/snippets/help_texts.html`, which both the admin forms and the inline
dialogs use, so a translation appears everywhere at once.
