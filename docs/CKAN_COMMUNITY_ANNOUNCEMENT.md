# CKAN community announcement

Text for the announcement of the 0.2.0 release. Post it as a discussion in the CKAN community.

## Title

Feedback wanted: ckanext-actor-registry 0.2.0 alpha, reusable publishers and contact points for CKAN metadata

## Body

We are looking for feedback on **ckanext-actor-registry**, an extension for
centrally managed, reusable publishers and contact points in CKAN metadata.

The problem we are exploring is simple: publisher and contact details are often
repeated across many datasets, which makes both data entry and later maintenance
unnecessarily expensive. The extension stores publishers and contact points once,
references them from datasets by stable IDs, and resolves the current registry
data for display and DCAT export. CKAN organizations remain a separate ownership
and authorization concept.

Version 0.2.0 includes:

- publisher and contact point management for logged-in editors, with merging of
  duplicates and permanent deletion for sysadmins;
- Scheming selectors, inline creation and editing while editing a dataset, record
  previews, the latest publisher and three recent contact points per user;
- dataset pages that show the publisher and contact points with their details, and
  a page per publisher and contact point that lists its datasets (paginated, and
  respecting private datasets);
- a worklist of datasets that are missing a publisher and/or a contact point, for
  activating the extension on a catalog that already has data;
- unique identifiers per identifier scheme, and one shared validation layer for
  the forms, the inline dialogs and the merge action;
- optional `foaf:Agent` and `vcard:Kind` output through ckanext-dcat, including
  `vcard:hasTelephone`, validated against the official DCAT-AP 3 SHACL shapes;
- an English interface with Swedish translations, and a runnable Docker Compose
  example with a smoke test.

The extension grew out of a Swedish municipal proof of concept, but the registry
model is intended to be useful across sectors, countries and organization types.
The automated suite runs on CKAN 2.11.1 and later 2.11 releases and on CKAN 2.12
(with ckanext-scheming 3.1.0). It is alpha software, meant for evaluation: there is
no formal security review or browser-based test suite yet, and no Action API for
registry administration (a deliberate choice; the reasoning is in the repository's
`docs/BACKLOG.md`). Parts of it were developed with AI assistance, which is
disclosed in `AI_ASSISTANCE.md`.

Before expanding the implementation, we would value feedback on three points:

1. Are you aware of an existing extension that already provides a comparable
   reusable publisher and contact point registry?
2. Does the separation between CKAN organization, publisher and contact point fit
   your catalog's model?
3. Which import/export, API, authorization and multilingual workflows would be
   most important for the next release?

Repository: https://github.com/bjornhagstrom/ckanext-actor-registry
Release: https://github.com/bjornhagstrom/ckanext-actor-registry/releases/tag/v0.2.0
