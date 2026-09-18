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

### Changed

- telephone URI normalization is shared by HTML helpers and RDF serialization;
- controlled theme and publisher-type URIs are explicitly typed as
  `skos:Concept` in RDF output.

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
- no registry Action API yet; browser and multi-version compatibility tests
  remain work for a later release.

[Unreleased]: https://github.com/OWNER/ckanext-actor-registry/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/OWNER/ckanext-actor-registry/releases/tag/v0.1.0
