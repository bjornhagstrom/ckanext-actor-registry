#!/bin/sh
# Runs on every container start, after CKAN has created its config file and
# before the web server starts.
set -e

# Scheming reads its schema and preset settings once, while CKAN loads its
# plugins, so they have to be in the ini file BEFORE that happens. Setting them
# through the `envvars` plugin (which must be last in CKAN__PLUGINS) is too late
# for Scheming. Writing them here with `ckan config-tool` avoids the ordering
# problem.
#
# Scheming path format: <python module>:<file>. An absolute file path does not work.
# The schema below ships inside the extension; copy it into a package of your own
# and point this at it to customise the dataset form.
ckan config-tool "$CKAN_INI" \
  "scheming.dataset_schemas = ckanext.actor_registry.examples:actor_registry_schema.yaml" \
  "scheming.presets = ckanext.scheming:presets.json"

# Create/upgrade the extension's tables. Safe to run on every start.
ckan -c "$CKAN_INI" db upgrade -p actor_registry
printf 'ckanext-actor-registry configured and migrated.\n'
