# Changelog

All notable changes to this project will be documented in this file. The format
is based on Keep a Changelog, and the project follows Semantic Versioning.

## [Unreleased]

### Changed

- Migration page: every group uses the same table, large or small. The datasets are ticked when they are included, one box in the heading ticks all or none (in
  between when some are ticked), and the headings sort the rows (dataset, organisation, source, name, email; a second click reverses). The ones that are not ticked
  are sent as the datasets to leave out. Without JavaScript the "Leave out" boxes work as before. Labels of checkboxes and radio buttons no longer get a colon from
  CKAN's stylesheet.
- Migration page: the button says how many datasets it will act on ("Apply to 42 datasets") and cannot be pressed for none.
- The registry is one tab, "Actor registry", in Administration; its pages show the Administration tabs (for sysadmins) and, under them, a
  submenu: Publishers, Contact points and, for those who may migrate, Migration and Cleanup, with a small number when something waits.
  `ckanext.actor_registry.admin_tab = false` turns the Administration tab off for portals that link to the registry from their own header.
- A tab "Actor registry" on the user's dashboard (for those who may edit at least one dataset) and a "Manage publishers" / "Manage contact
  points" link next to the two fields in the dataset form (opens in a new tab).
- The choices of "Missing:" on the publishers page show how many datasets each lists.
- The migration example schema (`actor_registry_migration_schema.yaml`) has a Landing page field (CKAN's own `url`).

### Fixed

- Migration page: linking or skipping the last group on the last page showed "Nothing remains to migrate." although groups
  were left; it now shows the last page that exists.

## [0.4.1] - 2026-10-08

No code or database changes since 0.4.0.

### Changed

- README: links the overview video on YouTube (90 seconds), at the top and in the documentation list.

## [0.4.0] - 2026-10-08

First beta. No code or database changes since 0.3.1.

### Changed

- The extension leaves alpha: the development status is now Beta (PyPI classifier, README, SECURITY.md,
  CONTRIBUTING.md). Still no formal security audit.
- README: migrating existing contact details (CKAN's Maintainer and Author fields) is now a section of its own near
  the top, with screenshots of the migration page and the cleanup page, and it is the first item in the feature list.
  A new "Languages" section says how to add your own language.
- Documentation: sixteen screenshots (all in English) and a GIF of merging two publishers in `docs/images/`.
  The README's captions and its text about the "missing" prompt match them.

## [0.3.1] - 2026-10-07

### Changed

- The package is on PyPI: `pip install ckanext-actor-registry` is the documented way to install it.
- The two i18n extraction tests are skipped when run from an installed package, which has no
  `babel.cfg`, instead of failing.

## [0.3.0] - 2026-10-07

### Upgrading from 0.2.x

- Run `ckan db upgrade -p actor_registry` (new tables, migrations 007 and 008).
- **List `actor_registry` before `scheming_datasets` in `ckan.plugins`.** 0.2.x
  documented the opposite order. CKAN takes a template from the plugin listed
  first, and the new `additional_info.html` override only applies when
  `actor_registry` comes first. In the old order the dataset page keeps showing
  Maintainer and Author while the DCAT export leaves them out, so the page and the
  export disagree.

### Added

- A shown Author is exported as `dct:creator` (DCAT-AP-SE: *producent*), so
  the export says what the dataset page says.
- *Cleanup* page (`/actor-registry/cleanup`): inactive publishers and contact
  points still used by datasets, and references to records that no longer
  exist; replace or remove them on the datasets you may edit.
- "Migrate to Actor Registry" (`/actor-registry/migrate`, a new tab): turns the
  contact details in CKAN's Maintainer and Author fields into shared contact
  points. Groups by email address, shows name variants and matching contact
  points; create, link to existing or skip, in rounds. Original fields are
  never changed; editors migrate their own datasets. Decisions are logged in
  a new table (migration `actor_registry_007`).
- The migration page shows a group of more than 25 datasets compactly: all of them are included, and
  the datasets to leave out are ticked in a scrollable list. Only those are posted, so a group of
  thousands of datasets is not refused by the web framework's form-size limit.
- Migration: *Changed since linking* lists linked datasets whose Maintainer or
  Author changed afterwards, with old and new values; update the contact
  point, link another, create a new one or keep it (migration
  `actor_registry_008` stores the values a decision was made on).
- Migration: *Close the migration* (sysadmins) hides Maintainer and Author in
  forms and on dataset pages and stops exporting them, at runtime and without
  deleting anything; it can be reopened. Asks for confirmation while datasets
  still lack a contact point. New `legacy_contact.html` form and display
  snippets for those fields.
- Setting `ckanext.actor_registry.legacy_contact_fields` (default `true`):
  when `false`, the DCAT export never uses CKAN's free-text contact fields
  (Maintainer, Author, ckanext-dcat's `contact_*` extras). Stored values are
  not changed.
- `docs/CATALOGUE_SETUPS.md`: common ways catalogues relate organizations,
  publishers and contact points, with a recommendation for each.
- A second example schema, `contact_points_only_schema.yaml`: organization and
  contact points without a publisher field, for catalogues where the owner
  organization is the publisher. With tests, including that the DCAT export
  then uses the organization as publisher.
- README section "Choosing your fields": why and how to choose between
  organization, publisher and contact points, how CKAN's own Author/Maintainer
  fields map, and that the schema decides which fields a dataset has (the
  optional legacy contact snippets can hide Maintainer and Author).

### Changed

- What visitors see is what is exported: the dataset page now shows an
  inactive publisher or contact point (the export already contained it), the
  export follows a merged publisher to its target (as the page did), and
  Maintainer/Author are not shown when the dataset has registry contact
  points (they were not exported). README: "What visitors see is what is
  exported", with the deliberate exceptions.
- The publisher is optional in `actor_registry_schema.yaml`. When it is
  optional and empty, the form explains that the organization is given as
  publisher in the DCAT export; the dataset page shows no publisher.
- The "missing" prompt on a dataset page follows the schema: it asks for a
  publisher only when the schema requires one, never for a field the schema
  lacks, and its heading names what is missing.
- The Edit and Delete buttons in the publisher and contact point lists are
  spaced, kept on one line, aligned with the row and identical in both lists;
  Delete is outlined instead of filled. Identifiers no longer wrap.
- The publisher and contact point pages are tidier: empty fields are no longer
  shown as "–", the dataset counts use real plural forms ("Linked to 1
  dataset", "Linked to 4 datasets", also on the delete and merge pages), each
  linked dataset shows its organization and when it was last updated, and the
  contact point breadcrumb names the contact point. The pages use the full
  width.

### Fixed

- Maintainer and Author that the schema does not show on the dataset page are
  no longer exported (ckanext-dcat used them as a contact point anyway).
- A deactivated publisher no longer locks the datasets that use it, the same
  way as for contact points; the form shows it marked inactive, and choosing
  an inactive or missing publisher gives a message that names it. Inactive
  publishers are no longer offered as "Belongs to organization" for a new
  contact point.
- A deactivated contact point no longer locks the datasets that use it: they
  can be saved, and the form shows it, marked inactive, instead of dropping it
  silently. Choosing an inactive contact point anew, or one that no longer
  exists, gives a message that names it.
- `ckanext.actor_registry.legacy_contact_fields` set to false in the ini file
  is read correctly after CKAN reloads its runtime settings (it can then be an
  empty string).
- A dataset with a broken stored `contact_point_ids` value (invalid JSON, as old
  imports can have) no longer makes the Publishers page and the worklist fail;
  such a value counts as no contact point, and a bare id as one.
- The DCAT export no longer adds Maintainer or Author as a second contact point
  when a dataset has registry contact points.
- Contact point and publisher references stored as JSON text are resolved like
  lists.
- Visitors who are not logged in no longer see the administration tabs
  (Sysadmins, Config, Trash) or the registry tabs on a publisher's or contact
  point's public page; logged-in users see only the registry tabs, sysadmins
  see all.

## [0.2.3] - 2026-10-01

### Changed

- The phone help text no longer refers to DCAT-AP-SE: "Include the country code, e.g. +46
  or +49, so the number works from other countries too." The README and the profile
  describe the telephone export as the usual vCard form, which ckanext-dcat itself lacks.
- The documentation speaks of DCAT-AP and national profiles based on it, with the Swedish
  DCAT-AP-SE only as an example of a national validator.
- A new language needs only its catalogue: the plugin offers every locale with a compiled
  `.mo` file in `i18n/` instead of a fixed list. A contributed language may be partial
  (untranslated strings show in English); only the maintained Swedish catalogues must be
  complete. A test checks that every `.mo` matches its `.po`, and CONTRIBUTING.md says how
  to contribute a language.

## [0.2.2] - 2026-10-01

### Fixed

- Swedish translations for the 13 strings added with contact point deletion
  (confirmation page, list filter, messages). They were missing from the
  `.pot` and `.po` files and showed in English on Swedish pages.
- New test: every string a fresh extraction finds must be translated in every
  shipped catalogue.

## [0.2.1] - 2026-09-22

### Fixed

- `examples/ckan-2.12/smoke_check.py`: the resource-creation step's POST response was
  discarded, so a server error there could still end in "All checks passed." The
  underlying cause was in the script itself: its hidden-field parser assumed
  `type="hidden"` came first in the tag, which is not true of CKAN 2.12's resource
  form, so the required (and CKAN-mandated) `id` field was silently dropped from the
  submission, causing a real HTTP 500 (`KeyError: 'id'` in CKAN core). The parser is
  now attribute-order independent, and the step's response is checked like every
  other step.
- `examples/ckan-2.12/smoke_check.py`: `CKAN_SITE_URL` is now read from the process
  environment first, falling back to `.env`, so a one-off `CKAN_SITE_URL=... python3
  smoke_check.py` (for a non-default port) is honoured instead of silently testing
  the wrong server.

### Added

- a regression test confirming that migration `006` fails clearly, and does not drop
  data, when a database already has active publishers with a duplicate
  (identifier_scheme, identifier) pair -- the behaviour the migration's own docstring
  and this changelog already documented, now exercised.

## [0.2.0] - 2026-09-21

The first tagged release. It follows the initial source-only snapshot (0.1.0, below) and contains
breaking changes: translation keys changed with the UI text ("actor" is now "publisher"), migration
`006` adds a unique index, and CKAN 2.11.0 and older are not supported.

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

[Unreleased]: https://github.com/bjornhagstrom/ckanext-actor-registry/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/bjornhagstrom/ckanext-actor-registry/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/bjornhagstrom/ckanext-actor-registry/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/bjornhagstrom/ckanext-actor-registry/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/bjornhagstrom/ckanext-actor-registry/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/bjornhagstrom/ckanext-actor-registry/releases/tag/v0.2.3
[0.2.2]: https://github.com/bjornhagstrom/ckanext-actor-registry/releases/tag/v0.2.2
[0.2.1]: https://github.com/bjornhagstrom/ckanext-actor-registry/releases/tag/v0.2.1
[0.2.0]: https://github.com/bjornhagstrom/ckanext-actor-registry/releases/tag/v0.2.0
[0.1.0]: https://github.com/bjornhagstrom/ckanext-actor-registry/tree/df14240
