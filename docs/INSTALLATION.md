# Installing on CKAN 2.11 and 2.12

This guide covers running `ckanext-actor-registry` on CKAN 2.11 or 2.12 together
with `ckanext-scheming`. It is based on a delivery test in a clean CKAN 2.12.0
environment and on the automated suite running on both release lines.

## Supported versions

| Component | Supported | Notes |
| --- | --- | --- |
| CKAN | **2.11.1 or later 2.11, and 2.12** | The full automated suite runs in CI on 2.11.1 (the oldest supported release), the newest 2.11 patch, and 2.12. The releases in between are not run separately. 2.11.0 cannot be tested: its official image has no working pytest plugin. |
| `ckanext-scheming` | **3.1.0** (recommended) | The latest release. 3.0.0 also works on 2.12 in the maintainer's development environment but is not part of the CI matrix. |
| `ckanext-dcat` | 2.4.4 | Only needed for the optional RDF export. |

`ckanext-scheming` has not yet published a release with explicit CKAN 2.12
support; that support exists on its `master` branch. Its released versions work
with this extension on 2.12, but CKAN logs a deprecation warning
(`h.uploads_enabled must be called with object_type ... In future this call will
cause an exception`) whenever the file-upload field is rendered. That is fixed
on scheming `master`, which the CI also runs against as an early warning.

## Compatibility status

| Area | Status |
| --- | --- |
| Full automated suite, including the official DCAT-AP 3 SHACL validation | Passes on CKAN 2.11.1, the newest 2.11 patch (2.11.6 at the time of writing) and 2.12.0, with scheming 3.1.0, and on 2.12.0 with scheming `master` |
| Install, plugin load, database migration | Passed in a clean CKAN 2.12.0 environment and by the suite on both versions |
| DCAT/RDF export | Exercised by the suite on both versions (Turtle, RDF/XML, JSON-LD, SHACL) |
| CKAN 2.11.0 | Not tested (see above) |
| CKAN 2.10 and older | Not supported |

## What is core and what is optional

- **Registry core** — publishers and contact points, their pages and forms, the
  merge and delete actions, the database tables. Needs only this extension.
- **Dataset fields (optional)** — the *Publisher* and *Contact points* fields
  on the dataset form and the public dataset page. These need
  `ckanext-scheming`; without it the registry works but no dataset fields
  appear.
- **DCAT/RDF export (optional)** — needs `ckanext-dcat` and the
  `actor_registry_euro_dcat_ap_3` profile. See
  [RDF_AND_INTEROPERABILITY.md](RDF_AND_INTEROPERABILITY.md).

## Install

```bash
pip install "ckanext-scheming==3.1.0"   # only for the dataset form fields
pip install -e /path/to/ckanext-actor-registry
```

If the extension cannot be imported after an editable install (`ModuleNotFoundError: No
module named 'ckanext.actor_registry'`), use a regular `pip install
/path/to/ckanext-actor-registry` instead. We saw this on the official CKAN 2.11.0 image, which
installs CKAN itself with an editable finder that claims the `ckanext` namespace.
## Configuration

```ini
ckan.plugins = ... scheming_datasets actor_registry ... envvars
scheming.dataset_schemas = ckanext.actor_registry.examples:actor_registry_schema.yaml
scheming.presets = ckanext.scheming:presets.json
```

Things that go wrong if missed (the example above handles all of them):

- **`envvars` must be last** in `ckan.plugins`.
- **Schema path format.** Scheming expects `python.module:file.yaml`. An
  absolute file path does not work. Your own schema must therefore live in an
  importable Python package.
- **Startup order.** Scheming reads its schema and presets once, while CKAN loads its plugins,
  so `scheming.dataset_schemas` and `scheming.presets` must already be in `ckan.ini` by then.
  Settings that arrive through the `envvars` plugin (which is last) come too late for it, and
  the dataset form silently falls back to CKAN's default fields. In a container setup, write
  them into the ini file with `ckan config-tool` in a start-up script that runs before the
  web server starts (the example's entrypoint script does exactly that).

## Database migration

```bash
ckan -c /srv/app/ckan.ini db upgrade -p actor_registry
```

Safe to run again on every start. Migration `006` adds a unique index on
`(identifier_scheme, identifier)` for **active** publishers. If your registry
already contains duplicate pairs the upgrade fails with an integrity error;
merge or edit the duplicates and run it again.

## The example schema

[`ckanext/actor_registry/examples/actor_registry_schema.yaml`](../ckanext/actor_registry/examples/actor_registry_schema.yaml)
is a working, localised (`en`, `sv`, `sv_SE`) example, exercised by the test
suite. It is an **integration example, not a universal metadata schema** —
copy it and decide per metadata profile what is required.

Two schema choices to make deliberately:

- **Publisher required or optional.** If required, an empty submission gives a
  clear validation error (no misleading blank option). If optional, choosing
  the empty option clears the previous link.
- **Reference validators.** Add `actor_registry_actor_exists` and
  `actor_registry_contactpoints_exist` to a field's `validators` so a dataset
  can only point at records that exist and are active, from any form or API
  call.

## Languages

The extension ships `sv` and `sv_SE` catalogues (English is the source
language). The site itself must offer the locale it uses (`ckan.locales_offered`
or `ckan.i18n.extra_locales`); CKAN core ships `sv` only. Field labels in your
own schema need `en`, `sv` and `sv_SE` entries — the form snippets already use
`h.scheming_language_text`.

## A runnable example

[`examples/ckan-2.12/`](../examples/ckan-2.12/) is a complete Docker Compose setup
(CKAN 2.12 or 2.11, PostgreSQL, Solr, Redis, ckanext-scheming 3.1.0 and this extension)
with a `.env.example`, a script that creates `.env` with random secrets, and a smoke
check (`smoke_check.py`) that creates a publisher, a contact point and a dataset through
the web form and verifies the dataset page and both registry pages. It has been run from a
clean state on CKAN 2.12.0 and 2.11.1 (the oldest supported release) and passes on
both, including when run twice and after a restart.
