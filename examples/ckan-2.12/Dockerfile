# Example image: CKAN + ckanext-scheming + ckanext-dcat (optional) + this extension.
#
# The build context is the ROOT of the ckanext-actor-registry repository (see
# docker-compose.yml), so the extension is installed from your checkout.
#
#   CKAN_VERSION    2.11 or 2.12
#   SCHEMING_SPEC   3.1.0 is the latest release; see docs/INSTALLATION.md
ARG CKAN_VERSION=2.12
FROM ckan/ckan-base:${CKAN_VERSION}

ARG SCHEMING_SPEC="ckanext-scheming==3.1.0"
ARG DCAT_SPEC="ckanext-dcat==2.4.4"

USER root
RUN pip install --no-cache-dir "${SCHEMING_SPEC}" "${DCAT_SPEC}"

COPY --chown=ckan-sys:ckan-sys . ${APP_DIR}/src_extensions/ckanext-actor-registry
RUN pip install --no-cache-dir ${APP_DIR}/src_extensions/ckanext-actor-registry

# Scripts in /docker-entrypoint.d run after CKAN's own initialisation and before
# the web server starts (a feature of the ckan-base image).
COPY --chown=ckan-sys:ckan-sys examples/ckan-2.12/docker-entrypoint.d/ /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.d/*.sh

USER ckan

# The base image's ckan.ini enables the `datastore` plugin. Its start-up script
# runs `ckan db init` with that file BEFORE it applies CKAN__PLUGINS from the
# environment, and datastore then fails without a datastore database. This
# example has no DataStore, so start from a minimal plugin list; CKAN__PLUGINS
# (docker-compose.yml) replaces it moments later.
RUN ckan config-tool "${CKAN_INI}" "ckan.plugins = envvars"
