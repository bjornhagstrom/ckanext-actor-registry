# Draft CKAN Ecosystem Catalog submission

The repository exists. Replace `RELEASE_URL` after the GitHub release for the
version below has been created.

## Name

ckanext-actor-registry

## Type

Extension

## Short description

Reusable registries for metadata publishers and contact points, with CKAN
Scheming widgets and optional DCAT serialization.

## Full description

ckanext-actor-registry lets CKAN catalogs centrally manage organizations,
people and contact functions that recur in dataset metadata. Datasets reference
stable registry IDs, while current publisher and contact details are resolved for
display and export. The extension keeps CKAN organizations separate from
metadata roles, supports management by logged-in editors (merging and deletion
for sysadmins) and inline creation while editing a dataset, and provides
per-user recent choices. Optional ckanext-dcat integration maps publishers to
FOAF agents and contact points to VCARD kinds.

## Repository

https://github.com/bjornhagstrom/ckanext-actor-registry

## Release

RELEASE_URL

## Version

0.2.1

## License

MIT

## Maintainer

Björn Hagström

## Compatibility

CKAN 2.11.1 and later 2.11 releases, and CKAN 2.12. The full automated suite,
including validation against the official DCAT-AP 3 SHACL shapes, runs on both
release lines. CKAN 2.11.0 and 2.10 and older are not supported.

## Dependencies

CKAN; ckanext-scheming (3.1.0 recommended) for dataset widgets; optional
ckanext-dcat and RDFLib for RDF serialization.

## Tags

metadata, publishers, contact-points, dcat, dcat-ap, foaf, vcard, scheming

## Maturity

Alpha / evaluation

## Primary language

Python. The user interface is in English, with Swedish (`sv`, `sv_SE`)
translations.
