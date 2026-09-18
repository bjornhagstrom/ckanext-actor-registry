# Draft CKAN Ecosystem Catalog submission

Replace `REPOSITORY_URL` and `RELEASE_URL` after the repository and GitHub
release exist.

## Name

ckanext-actor-registry

## Type

Extension

## Short description

Reusable registries for metadata actors and contact points, with CKAN Scheming
widgets and optional DCAT serialization.

## Full description

ckanext-actor-registry lets CKAN catalogs centrally manage organizations,
people and contact functions that recur in dataset metadata. Datasets reference
stable registry IDs, while current actor and contact details are resolved for
display and export. The extension keeps CKAN organizations separate from
metadata roles, supports sysadmin management and inline creation, and provides
per-user recent choices. Optional ckanext-dcat integration maps publishers to
FOAF agents and contact points to VCARD kinds.

## Repository

REPOSITORY_URL

## Release

RELEASE_URL

## Version

0.1.0

## License

MIT

## Maintainer

Björn Hagström

## Compatibility

Manually tested on CKAN 2.11.6. CKAN 2.10 and 2.12 are not yet verified.

## Dependencies

CKAN; ckanext-scheming for dataset widgets; optional ckanext-dcat and RDFLib for
RDF serialization.

## Tags

metadata, actors, publishers, contact-points, dcat, dcat-ap, foaf, vcard,
scheming

## Maturity

Alpha / evaluation

## Primary language

Python. The 0.1 user interface is Swedish-only; English and Swedish localization
is planned.
