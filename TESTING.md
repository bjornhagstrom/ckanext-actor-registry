# Test strategy

The registry stores shared metadata that is rendered in CKAN and serialized as
RDF. Tests therefore need to cover more than the HTML forms.

## Automated suite added for 0.1

| Area | Assertions |
| --- | --- |
| RDF contact points | `dcat:contactPoint`, `vcard:Kind`, name, email, URL and telephone triples use the configured stable contact URI. |
| RDF publishers | `dct:publisher` resolves to a separate `foaf:Agent` with name, identifier and homepage. |
| RDF reuse | Two datasets referring to the same contact produce the same RDF contact resource, not two unrelated blank nodes. |
| URI safety | An actor URI and a contact-point URI cannot be reused across the two registries. Editing a record may retain its own URI. |
| Web security | Management routes reject anonymous and ordinary users, POST requests require CSRF tokens, and URI collisions return HTTP 409. |
| Dataset projection | Stored registry IDs are resolved to the `contact` and `publisher` structures expected by ckanext-dcat. Missing references do not crash dataset display. |
| Preferences | The latest publisher and three most recent active contacts are returned in the intended order. |
| Lists | Inactive records are hidden from choices and ordinary choices are alphabetical. |
| Telephone links | Human-readable values are converted conservatively to `tel:` URIs for HTML and RDF. |
| Complete DCAT export | A dataset created through CKAN's Action API is exported through `dcat_dataset_show`; Turtle, RDF/XML and JSON-LD are parsed back and checked for the same actor and contact resources. |
| Database migration | The suite downgrades to the unpublished contact-point prototype, inserts a legacy record, upgrades to the actor registry and verifies that the record and all new tables survive; rerunning the current upgrade is harmless. |

The supported, reproducible test run builds an isolated CKAN 2.11 environment
with PostgreSQL, Solr and Redis. It also downloads the official DCAT-AP 3.0.1
SHACL shapes into the disposable test image:

```console
docker compose -f docker-compose.test.yml up \
  --build --abort-on-container-exit --exit-code-from tests
docker compose -f docker-compose.test.yml down -v
```

The first command must exit with status 0 and report all tests as passed. The
second command removes the disposable containers, network and database volume.
No production configuration or data is mounted into this environment.

The contact-point and publisher previews also have dependency-free JavaScript
regression tests for CKAN's jQuery/Select2 event path:

```console
node --test ckanext/actor_registry/tests/js/*.test.js
```

For contributors who already have a CKAN development environment, the same
suite can be run against an isolated PostgreSQL test database with:

```console
pip install -r dev-requirements.txt
pytest --ckan-ini=test.ini ckanext/actor_registry/tests
```

To validate the generated graph with another local copy of the official
DCAT-AP 3 SHACL file:

```console
DCAT_AP_3_SHACL_PATH=/path/to/dcat-ap-SHACL.ttl \
  pytest --ckan-ini=test.ini \
  ckanext/actor_registry/tests/test_rdf_endpoint.py
```

The test is skipped when the shapes path is not supplied. Keeping the official
shapes outside this MIT-licensed repository avoids silently vendoring a moving
third-party specification artifact.

DCAT-AP-SE is formally maintained through DIGG's RDForms specification rather
than a repository-local SHACL file. Validate the deployed catalog export with
the toolkit at `https://sandbox.admin.dataportal.se/toolkit` before claiming
DCAT-AP-SE conformance. This complements, rather than replaces, the automated
DCAT-AP 3 SHACL test.

Fast tests that do not alter the database can be selected with:

```console
pytest --ckan-ini=test.ini -m "not integration" ckanext/actor_registry/tests
```

Never point CKAN tests at a production or development database containing data.

## Next automated tests before a stable release

1. Additional form tests: validation errors preserve values, blank names are
   rejected and edits retain their existing URI when the URI field is blank.
2. Browser tests: previews update after selection, inline creation selects the
   new item, email/telephone links are correct, keyboard operation and focus
   management work, and recent groups do not duplicate alphabetical choices.
3. RDF import/reconciliation tests if import is implemented: match stable URIs,
   never silently create duplicates, and require review for ambiguous matches.
4. Compatibility matrix in CI for supported CKAN, Python, Scheming and
   ckanext-dcat versions.

## Manual release checks

- Create and edit actors and contact points with Swedish characters.
- Select one publisher and several contacts while creating a dataset.
- Confirm recent choices are private to each CKAN user.
- Deactivate a selected registry record and verify existing dataset pages still
  resolve it while new forms do not offer it.
- Export the same dataset from the live DCAT endpoint and validate it with the
  DCAT-AP 3 SHACL shapes and the current DCAT-AP-SE validator.
- Verify that actor and contact URIs remain distinct even when the contact is
  linked to that actor.
