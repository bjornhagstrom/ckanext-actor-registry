# Test strategy

The registry stores shared metadata that is rendered in CKAN and serialized as
RDF. Tests therefore need to cover more than the HTML forms.

## Automated suite

| Area | Assertions |
| --- | --- |
| RDF contact points | `dcat:contactPoint`, `vcard:Kind`, name, email, URL and telephone triples use the configured stable contact URI. |
| RDF publishers | `dct:publisher` resolves to a separate `foaf:Agent` with name, identifier and homepage. |
| RDF reuse | Two datasets referring to the same contact produce the same RDF contact resource, not two unrelated blank nodes. |
| URI safety | A publisher URI and a contact-point URI cannot be reused across the two registries. Editing a record may retain its own URI. |
| Web security | Management routes reject anonymous and ordinary users, POST requests require CSRF tokens, and URI collisions return HTTP 409. |
| Dataset projection | Stored registry IDs are resolved to the `contact` and `publisher` structures expected by ckanext-dcat. Missing references do not crash dataset display. |
| Preferences | The latest publisher and three most recent active contacts are returned in the intended order. |
| Lists | Inactive records are hidden from choices and ordinary choices are alphabetical. |
| Telephone links | Human-readable values are converted conservatively to `tel:` URIs for HTML and RDF. |
| Complete DCAT export | A dataset created through CKAN's Action API is exported through `dcat_dataset_show`; Turtle, RDF/XML and JSON-LD are parsed back and checked for the same actor and contact resources. |
| Database migration | The suite downgrades to the unpublished contact-point prototype, inserts a legacy record, upgrades to the actor registry and verifies that the record and all new tables survive; rerunning the current upgrade is harmless. |
| Input validation | Every field has a length limit that matches its database column (too long is a message, not an error page); emails are checked with CKAN's own validator, web addresses and URIs must be absolute; a value unchanged from what is stored is not re-validated, so older records stay editable; the merge action applies the same rules and changes nothing when they fail. |
| Unique identifiers | An identifier and its scheme must be given together and are unique among active publishers, in the forms, the inline dialogs and the database; retired publishers do not count. |
| Dataset display | The dataset page shows a publisher and contact points by name and details, never by ID; a merged publisher shows as its survivor; inactive or missing records are left out; a stored `javascript:` or other non-http(s) address is never rendered as a link. |
| Dataset lists | Publisher and contact point pages, their "Show all" pages, the delete confirmations and the worklist read datasets from the database (not the search index), paginate, sort A-Z and never show a private dataset to someone who may not see it. |
| Worklist | The *Missing:* choices (both, publisher, contact point, either) list the right datasets, and pagination keeps the choice. |
| Translations | English, `sv` and `sv_SE` render help texts and messages; the `sv` and `sv_SE` catalogues stay identical; extraction finds every template string. |
| CKAN 2.11 and 2.12 | Queries that read a dataset's extras work with both storage layouts (`package_extra` on 2.11, `package.extras` on 2.12). |
| Example schema | The shipped example schema loads and works. |

The supported, reproducible test run builds an isolated CKAN environment with
PostgreSQL, Solr and Redis. It also downloads the official DCAT-AP 3.0.1 SHACL
shapes into the disposable test image. The CKAN release line, and the
ckanext-scheming and ckanext-dcat versions, are build arguments; the defaults are
CKAN 2.12 with ckanext-scheming 3.1.0 and ckanext-dcat 2.4.4:

```console
# CKAN 2.12 (the default)
docker compose -f docker-compose.test.yml up \
  --build --abort-on-container-exit --exit-code-from tests
docker compose -f docker-compose.test.yml down -v

# CKAN 2.11 (the newest patch), or a specific release such as the oldest supported, 2.11.1.
# The Solr image only has a tag per release line, so a specific patch needs SOLR_VERSION too.
CKAN_VERSION=2.11.1 SOLR_VERSION=2.11 docker compose -p ar-tests-2111 -f docker-compose.test.yml up \
  --build --abort-on-container-exit --exit-code-from tests
CKAN_VERSION=2.11.1 SOLR_VERSION=2.11 docker compose -p ar-tests-2111 -f docker-compose.test.yml down -v

# CKAN 2.12 against ckanext-scheming's unreleased master
SCHEMING_SPEC="ckanext-scheming @ https://codeload.github.com/ckan/ckanext-scheming/tar.gz/refs/heads/master" \
  docker compose -p ar-tests-master -f docker-compose.test.yml up \
  --build --abort-on-container-exit --exit-code-from tests
```

Each run must exit with status 0 and report all tests as passed. The `down -v`
command removes the disposable containers, network and database volume. Give
runs of different CKAN versions different project names (`-p`) so they do not
share containers. No production configuration or data is mounted into this
environment. GitHub Actions runs the same combinations plus the oldest supported
CKAN (`.github/workflows/test.yml`); the scheming-master one is allowed to fail.

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

1. Browser tests: previews update after selection, inline creation selects the
   new item, email/telephone links are correct, keyboard operation and focus
   management work, and recent groups do not duplicate alphabetical choices.
2. RDF import/reconciliation tests if import is implemented: match stable URIs,
   never silently create duplicates, and require review for ambiguous matches.
3. A wider compatibility matrix in CI (Python versions, more Scheming and
   ckanext-dcat versions); CKAN 2.11.1, the newest 2.11 patch and 2.12 are covered.

## Manual release checks

- Create and edit publishers and contact points with Swedish characters.
- Select one publisher and several contacts while creating a dataset.
- Confirm recent choices are private to each CKAN user.
- Deactivate a selected registry record and verify existing dataset pages still
  resolve it while new forms do not offer it.
- Export the same dataset from the live DCAT endpoint and validate it with the
  DCAT-AP 3 SHACL shapes and the current DCAT-AP-SE validator.
- Verify that publisher and contact URIs remain distinct even when the contact
  belongs to that publisher.
- Run `examples/ckan-2.12` and its `smoke_check.py` from a clean state on the oldest
  and the newest supported CKAN releases.
