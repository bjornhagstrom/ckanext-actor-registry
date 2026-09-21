# Example: CKAN + ckanext-scheming + ckanext-actor-registry with Docker Compose

A complete, runnable setup that you can use to try the extension or as a starting
point for your own. It runs on **CKAN 2.12 or 2.11**, with **ckanext-scheming 3.1.0**.

> **This is an integration example, not a production deployment.** It has no HTTPS,
> no backups and no DataStore/DataPusher. The dataset schema it uses
> (`ckanext/actor_registry/examples/actor_registry_schema.yaml`) is an example of how
> to wire the registry into a Scheming schema; it is **not** a universal metadata
> schema. Copy it and decide which fields your catalogue needs.

## What you need

Docker with Compose v2, and a checkout of this repository (the image is built from
it, so the extension is installed from your working copy).

## Run it

```console
cd examples/ckan-2.12
./setup.sh                      # creates .env with random secrets (never overwrites an existing one)
docker compose up -d --build    # the first build takes a few minutes
```

CKAN is then at <http://localhost:5000>. Log in as `admin`; its password is
`CKAN_SYSADMIN_PASSWORD` in your `.env`. If port 5000 is taken, change `CKAN_PORT` and
`CKAN_SITE_URL` in `.env` before starting.

To check the installation, run:

```console
python3 smoke_check.py
```

It logs in, checks that both plugins are loaded and the registry tables exist, that the
dataset form has the *Publisher* and *Contact points* fields, and that a publisher can be
created and then shows up on the dataset form. It leaves a "Smoke test publisher" and a
"Smoke test organization" behind.

## Try the extension

1. **Create an organization** (*Organizations → Add Organization*). CKAN shows no
   dataset form until at least one organization exists.
2. Open **`/actors`** and create a publisher, then **`/contactpoints`** and create a
   contact point. Or create them from inside the dataset form, using the *Create new
   publisher* / *Create new contact point* buttons.
3. **Add a dataset**: choose the publisher and contact points from the pickers. The
   dataset page shows their details, and the publisher's page lists its datasets.
4. Add `/sv/` to any URL for the Swedish texts.

## Use CKAN 2.11 instead

Set `CKAN_VERSION=2.11` in `.env`, then `docker compose down -v` and
`docker compose up -d --build`. Everything else is the same.

## How it is put together, and why

- **`Dockerfile`** builds on `ckan/ckan-base`, installs ckanext-scheming (and
  ckanext-dcat, which the optional RDF export needs) and installs the extension from
  your checkout.
- **`docker-entrypoint.d/10_configure_actor_registry.sh`** runs on every start. It
  writes the Scheming settings into `ckan.ini` and runs
  `ckan db upgrade -p actor_registry`, which creates and upgrades the extension's tables
  (safe to repeat).
- **`docker-compose.yml`** starts CKAN, PostgreSQL, Solr and Redis. All settings are in
  the `environment:` block, and secrets come from `.env`.

Things that go wrong if you change the setup and miss them:

- **`envvars` must be the last plugin** in `CKAN__PLUGINS`.
- **Scheming settings are set in the entrypoint script, not through `envvars`.**
  Scheming reads its schema and presets once, while CKAN loads its plugins. Settings that
  arrive through the `envvars` plugin (which is last) arrive too late for it, so the
  dataset form would silently fall back to CKAN's default fields.
- **The Scheming schema path is `python.module:file.yaml`**, for example
  `ckanext.actor_registry.examples:actor_registry_schema.yaml`. An absolute file path does
  not work. To use your own schema, put it in a Python package that is installed in the
  image and point `scheming.dataset_schemas` at it.
- **The image's `ckan.ini` enables the `datastore` plugin**, and its start-up script runs
  `ckan db init` with that file before it applies `CKAN__PLUGINS`. Without a DataStore
  database that fails on the very first start, so the `Dockerfile` resets the plugin list
  to `envvars` at build time. If you add DataStore, give CKAN the datastore database URLs
  and drop that line.
- **The CKAN images are amd64-only**, hence `platform: linux/amd64` (needed on Apple
  silicon; it does nothing on amd64 machines).

## About the scheming version

3.1.0 is the latest ckanext-scheming release. Released versions work on CKAN 2.12, but CKAN
logs a deprecation warning about `h.uploads_enabled` when the file-upload field is
rendered; that is fixed on scheming's `master` branch. To try it, set
`SCHEMING_SPEC="ckanext-scheming @ https://codeload.github.com/ckan/ckanext-scheming/tar.gz/refs/heads/master"`
in `.env`. See [`docs/INSTALLATION.md`](../../docs/INSTALLATION.md) for what is tested.

## Stop and clean up

```console
docker compose down        # stop, keep the data
docker compose down -v     # stop and delete the database, search index and uploads
```
