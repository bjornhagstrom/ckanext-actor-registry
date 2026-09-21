# ckanext-actor-registry 0.2.0

This is the first tagged release of ckanext-actor-registry, a CKAN extension for
centrally managed, reusable publishers and contact points. It follows the initial
source-only snapshot (0.1.0, published on 2026-09-18 without a release) and contains
breaking changes; see "Upgrading from the 0.1.0 snapshot" below.

Instead of copying publisher and contact details into every dataset, catalogs can
store each record once and reference it from metadata. This makes recurring metadata
easier to enter and central changes easier to maintain. CKAN organizations remain
separate and continue to control ownership and access.

## What is new since the 0.1.0 snapshot

- **CKAN 2.11.1 and later 2.11 releases, and CKAN 2.12**, with ckanext-scheming 3.1.0
  recommended. The full automated suite, including validation against the official
  DCAT-AP 3 SHACL shapes, runs on both release lines; CI runs it on 2.11.1, the newest
  2.11 patch and 2.12. See [docs/INSTALLATION.md](INSTALLATION.md).
- **A runnable Docker Compose example** with a smoke test that creates a publisher, a
  contact point and a dataset through the web form:
  [examples/ckan-2.12](../examples/ckan-2.12/README.md).
- **"Publisher" instead of "actor"** in all user-facing text. The interface is English by
  default with Swedish (`sv`, `sv_SE`) translations.
- **What visitors see:** a dataset page shows its publisher and contact points with their
  readable details instead of stored ids; publisher and contact point pages list their
  datasets (paginated, and respecting private datasets).
- **Data quality:** an identifier plus its scheme is unique among active publishers;
  emails, web addresses, URIs, phone numbers and lengths are validated by one shared layer
  that also protects the merge action; opt-in validators keep datasets from pointing at
  records that no longer exist.
- Localised help texts in the forms and dialogs, and safer handling of stored links.

## Upgrading from the 0.1.0 snapshot

- Run `ckan -c /path/to/ckan.ini db upgrade -p actor_registry`. Migration `006` adds a
  unique index on the identifier and scheme of active publishers and **fails if duplicate
  pairs already exist**; merge or edit them first.
- **Translation keys changed** with the UI text ("actor" became "publisher"). Translations
  you maintain for the old strings must be updated.
- CKAN 2.11.0 and older versions are not supported.

## Known limitations

This is evaluation software. There is no Action API for registry administration, and no
import/export command. Users who can see a private dataset only as a CKAN *dataset
collaborator* do not see it in the registry's dataset lists. See the README and the
changelog for the full list.

The project is MIT licensed. Its code and documentation were developed by Björn Hagström
with assistance from OpenAI's ChatGPT and Codex and from Anthropic's Claude Code; the
human maintainer reviewed the release and accepts responsibility for it.
