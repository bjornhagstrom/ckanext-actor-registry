# Changelog

All notable changes to this project will be documented in this file. The format
is based on Keep a Changelog, and the project follows Semantic Versioning.

## [Unreleased]

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

### Changed

- telephone URI normalization is shared by HTML helpers and RDF serialization;
- controlled theme and publisher-type URIs are explicitly typed as
  `skos:Concept` in RDF output;
- `CONTRIBUTING.md`'s development priorities no longer list a full Action API;
  see `docs/BACKLOG.md` for why that was deliberately deprioritized rather
  than deferred.

## [0.1.0] - Unreleased

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

- automated verification currently covers CKAN 2.11.6 only;
- browser and multi-version compatibility tests and a formal security review
  remain work for a later release. A full registry Action API was
  deliberately deprioritized rather than deferred -- see
  `docs/BACKLOG.md` and `CONTRIBUTING.md`.

[Unreleased]: https://github.com/bjornhagstrom/ckanext-actor-registry/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/bjornhagstrom/ckanext-actor-registry/releases/tag/v0.1.0
