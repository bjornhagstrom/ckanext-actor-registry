# Instructions for AI assistants installing ckanext-actor-registry

This file is for an AI assistant (or a person in a hurry) asked to install
this extension in an existing CKAN. It is short on purpose; the details are in
[docs/INSTALLATION.md](docs/INSTALLATION.md). Developing the extension itself
is covered by [CONTRIBUTING.md](CONTRIBUTING.md) and [TESTING.md](TESTING.md).

## Ask, do not guess

Find out these facts from the configuration, and ask the catalogue owner
where the configuration does not tell you:

1. Is `ckanext-scheming` in `ckan.plugins`, and which schema does
   `scheming.dataset_schemas` name? That is the source schema. Without
   Scheming the source is `ckanext.scheming:ckan_dataset.yaml`.
2. Is `ckanext-dcat` installed and in `ckan.plugins`? Not every catalogue has
   it. Without it, skip everything about the DCAT profile; do not install
   ckanext-dcat unless the owner asks for it.
3. Do datasets use CKAN's free "Custom fields" (extras)? A Scheming schema
   only keeps what it lists: a form save removes the rest. Ask which ones to
   keep, and add them as fields to the copy before switching.
4. Can the publisher differ from the owner organization? Then the owner wants
   the publisher field (see [docs/CATALOGUE_SETUPS.md](docs/CATALOGUE_SETUPS.md)).

## Do

- Write the schema with the tool, from the source schema:
  `python -m ckanext.actor_registry.schema_tool SOURCE -o FILE`.
  Read the result and tell the owner what changed (the tool prints it).
- Point Scheming at it as `file:///absolute/path.yaml` (a bare path does not
  work), in `ckan.ini` before CKAN starts, not through the `envvars` plugin.
- Keep the plugin order: `actor_registry` before `scheming_datasets`,
  `envvars` last; with ckanext-dcat, use the profile
  `actor_registry_euro_dcat_ap_3` and dcat's presets.
- Run `ckan db upgrade -p actor_registry`.
- Check one existing dataset afterwards: its edit form shows *Contact points*
  and the old contact fields with their values, its page still shows the
  contact details and, with ckanext-dcat, its export too. Tell the owner
  about other differences on the page (Scheming shows only the schema's
  fields).

## Do not

- Do not point `scheming.dataset_schemas` at one of this extension's example
  schemas on a catalogue that has datasets: they lack fields such as keywords,
  licence and version, and the next form save clears those values.
- Do not remove the old contact fields from the schema. The tool keeps them as
  legacy fields so that their values survive; removing them loses the values
  on the next save.
- Do not close the migration (`/actor-registry/migrate`) or change
  `ckanext.actor_registry.legacy_contact_fields` for the owner. Closing hides
  the old contact fields for everyone; it is the owner's decision once the
  contact details are moved.
- Do not create or link contact points for the owner on the migration page.
  The page shows suggestions; an editor decides each one.
- Do not switch the schema of a production catalogue without a database
  backup and a try on a copy first.
