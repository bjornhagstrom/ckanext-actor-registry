# Contributing

Thank you for helping improve ckanext-actor-registry. Version 0.1 is an alpha,
so bug reports, compatibility results and design feedback are especially useful.

## Before opening an issue

- search existing issues;
- include the CKAN, Python, ckanext-scheming and ckanext-dcat versions used;
- describe the expected and actual result;
- include reproducible steps and relevant logs with credentials and personal
  data removed.

Use a private security report instead of a public issue for vulnerabilities; see
[SECURITY.md](SECURITY.md).

## Pull requests

1. Discuss substantial behavior or data-model changes in an issue first.
2. Keep each pull request focused.
3. Add or update tests when changing behavior.
4. Update the README and changelog when user-visible behavior changes.
5. Internationalize all new user-visible strings: wrap them in `_(...)`
   with English source text (`from ckan.common import _` in Python,
   `{{ _("...") }}` in templates; JavaScript strings go through a
   `data-i18n-*` attribute rendered server-side instead, see
   `assets/js/actor-quick-create.js` for the pattern), then add the
   Swedish `msgstr` to
   `ckanext/actor_registry/i18n/sv/LC_MESSAGES/ckanext-actor-registry.po`
   and recompile with `pybabel compile -d ckanext/actor_registry/i18n -D
   ckanext-actor-registry` (also wired into `dev-install-extras.sh`, so a
   dev-stack rebuild picks it up too). To re-extract the full catalog
   from scratch, run `pybabel extract -F babel.cfg -o ckanext/actor_registry/i18n/ckanext-actor-registry.pot .` from this
   repo's root -- see `babel_ckan_tag_shims.py` first if that ever
   silently drops a template's strings again.
6. Confirm that migrations preserve existing data and provide a downgrade where
   practical.
7. State whether and how generative AI tools assisted the contribution. The
   contributor remains responsible for reviewing the work and for its license
   and provenance.

By submitting a contribution, you agree that it may be released under the MIT
license used by this repository and confirm that you have the right to submit
it.

## Development priorities for 0.2

- automated model, authorization, form and RDF serialization tests;
- Action API support with explicit authorization functions;
- CKAN 2.10, 2.11 and 2.12 compatibility testing;
- documented import and export workflows.

All contributors must follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
