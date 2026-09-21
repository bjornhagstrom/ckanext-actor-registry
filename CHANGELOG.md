# Changelog

All notable changes to this project will be documented in this file. The format
is based on Keep a Changelog, and the project follows Semantic Versioning.

## [Unreleased]

## [0.2.0] - Unreleased

The first tagged release. It follows the initial source-only snapshot (0.1.0, below) and contains
breaking changes: translation keys changed with the UI text ("actor" is now "publisher"), migration
`006` adds a unique index, and CKAN 2.11.0 and older are not supported. Set the release date here
when tagging (see `docs/PUBLISHING.md`).

### Added

- an initial automated test suite for registry behavior, dataset projection and
  DCAT-AP 3 RDF serialization;
- a migration rehearsal that preserves records from the unpublished contact
  point prototype;
- Action API end-to-end tests for Turtle, RDF/XML and JSON-LD plus optional
  validation with the official DCAT-AP 3 SHACL shapes;
- documented RDF and interoperability design decisions;
- cross-registry validation preventing actors and contact points from sharing a
  URI.
- a GitHub Actions CI workflow running the automated test suite and the
  dependency-free JS regression tests on every push and pull request;
- a README section documenting how to activate the extension on an existing
  installation that already has datasets (the `/actors` worklist and the
  inline per-dataset fix-it prompt);
- `setup.py` project metadata (`url`, `author`, `project_urls`) now that the
  project has a public repository.
- permanent actor deletion (`actor_registry_actor_delete`, sysadmin-only),
  for actors -- active or already merged/retired -- that are no longer
  needed. Clears the actor as publisher on any dataset that had it, and
  decouples (does not delete) any contact points it owned;
- merged/retired actors are now hidden by default on `/actors`, with a
  checkbox to show them again.
- permanent contact point deletion (`actor_registry_contactpoint_delete`,
  sysadmin-only), mirroring actor deletion: removes the contact point
  from any dataset's `contact_point_ids`, leaves an owning actor
  unaffected;
- inactive contact points are now hidden by default on `/contactpoints`,
  with a checkbox to show them again.
- public dataset display snippets (`actor.html`, `contactpoints.html`) showing
  readable publisher and contact point details instead of stored ids; merged
  actors resolve to their survivor, inactive or missing references render
  nothing;
- `(identifier_scheme, identifier)` uniqueness among active actors, with
  server-side validation in forms and inline dialogs, a localised conflict
  message naming the existing actor, and a partial unique index (migration
  `006`; upgrading fails if duplicates already exist);
- email, URL, phone and kind validation/normalisation in every form and dialog. Emails are
  checked with CKAN's own `email_validator` (plus a dot in the domain, which CKAN itself does
  not require); a value that is unchanged from what is stored is not re-validated, so records
  saved before a rule existed can still be edited;
- opt-in validators `actor_registry_actor_exists` and
  `actor_registry_contactpoints_exist` for dataset schemas;
- localised field help texts shared by the admin forms and inline dialogs,
  a `sv_SE` catalogue, and a localised example schema
  (`ckanext/actor_registry/examples/`);
- `docs/INSTALLATION.md`, an install and compatibility guide for CKAN 2.11 and 2.12;
- `docs/TRANSLATIONS.md`, a guide to the translation catalogues and how to change or add strings
  (it replaces the internal `I18N_PLAN.md`);
- `examples/ckan-2.12/`, a runnable Docker Compose example (CKAN 2.11 or 2.12, PostgreSQL,
  Solr, Redis, ckanext-scheming 3.1.0 and this extension) with a smoke test;
- supported CKAN releases: 2.11.1 and later 2.11 patches, and 2.12. CI runs the full suite on
  2.11.1 (the oldest supported), the newest 2.11 patch and 2.12 with ckanext-scheming 3.1.0,
  and on 2.12 against scheming `master` (allowed to fail); `Dockerfile.test` and
  `docker-compose.test.yml` take the CKAN and scheming versions as build arguments.
- Swedish translations for the delete-confirmation pages (they were English-only);
- "Belongs to organization" can now be set in the inline contact point dialog
  (previously only in the admin form), with the same help text; a link must
  point at an existing, active actor.
- a contact point's page lists the datasets it is linked to, and an actor's page
  previews its first 10 (as publisher, and via its contact points) with a
  "Show all N" link to a paginated list (20 per page, A-Z) at
  `/actors/<id>/datasets` and `/contactpoints/<id>/datasets`. The lists are read
  from the database, not the search index, and respect dataset visibility:
  private datasets are shown only to sysadmins and members of the owning
  organisation.

### Changed

- documentation brought up to date for 0.2.0: the README is rewritten for the "publisher"
  wording, with a Documentation index and a note on each screenshot link (the screenshots are
  being retaken); `docs/BACKLOG.md` is now a short English backlog; CONTRIBUTING, SECURITY,
  TESTING, the release notes, the community announcement draft and the catalog submission
  draft are updated;
- validation now lives in ONE shared layer (`validation.py`) instead of in the views: the rules are
  CKAN validators collected in schemas that CKAN's own `navl` machinery runs, giving ordinary CKAN
  error dicts. The full forms, the inline dialogs and the merge action all use it, and an API added
  later would too;
- telephone URI normalization is shared by HTML helpers and RDF serialization;
- controlled theme and publisher-type URIs are explicitly typed as
  `skos:Concept` in RDF output;
- `CONTRIBUTING.md`'s development priorities no longer list a full Action API;
  see `docs/BACKLOG.md` for why that was deliberately deprioritized rather
  than deferred.
- the worklist of datasets that lack something, on `/actors`, previews 10 with an exact total and a
  "Show all" link to a paginated page (`/actors/unlinked-datasets`). A *Missing:* choice picks
  which datasets it lists: missing both a publisher and a contact point (the default), only a
  publisher, only a contact point, or either (`?missing=both|publisher|contact_point|either`).
  Like the other registry lists it reads from the database, not the search index;
- the contact point list links each name to the contact point's page, like the publisher list;
- a publisher is no longer presented as a contact point: its page, its "show all"
  page, the delete confirmation and the merge summary list only the datasets it
  publishes, not datasets that merely use a contact point that belongs to it;
- the contact point field "Belongs to actor" is now "Belongs to organization"
  (sv: "Tillhör organisation"), and the row is hidden on the public contact
  point page when no link is set;
- several contact points on a dataset page are visually separated.
- on the dataset page a publisher's type, web address, email and description are
  shown on their own lines under its name (values only, like the contact points)
  instead of the web address in parentheses;
- UI text now says "publisher" instead of "actor" throughout, in English and
  Swedish ("utgivare", not "aktör"), matching the dataset form. Only visible
  text changes; URLs, action names and code identifiers keep "actor". The
  translation catalogue keys change with the English text, so out-of-tree
  translations of the old strings need updating;

### Fixed

- `actor_registry_actor_merge` wrote the chosen field values (email, URL, identifier, ...) onto the
  surviving publisher without validating them, and an identifier that clashed with a third
  publisher's surfaced as a database error. The chosen values now pass the same rules as any other
  edit, and a violation is a `ValidationError` on `fields`, with nothing changed;
- an input longer than its database column (a name or identifier over 255 characters, an email
  over 320, a phone number over 100) crashed with a database error, i.e. an HTTP 500. Every
  field now has a maximum length and shows a translated message instead;
- the Persistent URI and Type fields of a publisher, and the URI of a contact point, were not
  validated on the server; they must now be absolute URIs (`http://`, `https://` or `urn:`);
- stored web addresses and URIs are only turned into links when CKAN's own `h.is_url` accepts
  them (also in the JavaScript previews, which allow only http(s)); anything else, e.g. a `javascript:` value from a
  row saved before validation existed, is shown as plain text instead of a clickable link;
- the queries that find the datasets linked to a publisher or contact point read the
  dataset's extras from `package.extras`, a jsonb column that only exists in CKAN 2.12;
  on CKAN 2.11 (where extras live in the `package_extra` table) they failed with
  `column "extras" does not exist`. Both layouts are now supported;
- the test image no longer needs `wget` (it is gone from the CKAN 2.12 images) and no
  longer depends on the host's file modes.
- merging actors would have failed to hand the surviving actor the merged
  actor's identifier once identifiers became unique; the merged actor is now
  retired first;
- `MANIFEST.in` now packages the translation catalogues and the example schema.

### Known limitations

- the dataset lists on publisher and contact point pages only include private datasets
  that the visitor may see as a sysadmin or as a member of the dataset's organization.
  Users who can see a private dataset only as a CKAN *dataset collaborator*
  (`ckan.auth.allow_dataset_collaborators`, off by default) do not see it in these lists;
  nothing is revealed to anyone who should not see it.

## [0.1.0] - 2026-09-18

Published as source only (the initial standalone snapshot); no release or tag was created.

### Added

- reusable actor and contact point registries;
- sysadmin management pages and inline creation from Scheming forms;
- publisher and contact point selectors with record previews;
- per-user latest-publisher and recent-contact-point convenience choices;
- stable dataset references resolved at display and export time;
- optional European DCAT-AP 3 profile extension with VCARD telephone output;
- Alembic migrations for all extension-owned tables;
- documentation for installation, integration, security and contribution;
- English source strings throughout templates, Python and JavaScript, with a
  compiled Swedish translation catalog using CKAN's own gettext-based
  translation mechanism (`ITranslation`), the same one `ckanext-skelleftea`
  uses.

### Known limitations

- automated verification covers CKAN 2.11.1 and later 2.11 patches and CKAN 2.12 (see
  `docs/INSTALLATION.md`; this line said "2.11.6 only" before CI was extended);
- browser and multi-version compatibility tests and a formal security review
  remain work for a later release. A full registry Action API was
  deliberately deprioritized rather than deferred -- see
  `docs/BACKLOG.md` and `CONTRIBUTING.md`.

[Unreleased]: https://github.com/bjornhagstrom/ckanext-actor-registry/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/bjornhagstrom/ckanext-actor-registry/releases/tag/v0.2.0
[0.1.0]: https://github.com/bjornhagstrom/ckanext-actor-registry/tree/df14240
