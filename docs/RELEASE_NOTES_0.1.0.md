# ckanext-actor-registry 0.1.0

This is the first public alpha release of ckanext-actor-registry, a CKAN
extension for centrally managed, reusable actors and contact points.

Instead of copying publisher and contact details into every dataset, catalogs
can store each record once and reference it from metadata. This makes recurring
metadata easier to enter and central changes easier to maintain. CKAN
organizations remain separate and continue to control ownership and access.

The release includes Scheming form widgets, inline sysadmin creation, record
previews, recent choices per user and optional DCAT serialization through
ckanext-dcat. It was developed from a municipal proof of concept, but its core
model is intentionally independent of country and organization type.

This is evaluation software. It has been manually tested with CKAN 2.11.6, the
UI is currently Swedish-only, and the initial automated suite does not yet cover
browser behavior, migration history or a broad compatibility matrix. Feedback
on the model, installation, DCAT mapping and workflows is especially welcome.

The project is MIT licensed. Its initial code and documentation were developed
by Björn Hagström with assistance from OpenAI's ChatGPT and Codex; the human
maintainer reviewed the release and accepts responsibility for it.
