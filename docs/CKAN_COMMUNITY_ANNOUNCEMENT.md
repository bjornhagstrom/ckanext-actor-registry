# Draft CKAN community announcement

## Title

Feedback wanted: ckanext-actor-registry 0.1.0 alpha

## Body

We are preparing the first public alpha release of
**ckanext-actor-registry**, an extension for centrally managed, reusable actors
and contact points in CKAN metadata.

The problem we are exploring is simple: publisher and contact details are often
repeated across many datasets, which makes both data entry and later maintenance
unnecessarily expensive. The extension stores actors and contact points once,
references them from datasets by stable IDs, and resolves current registry data
for display and DCAT export. CKAN organizations remain a separate ownership and
authorization concept.

Version 0.1.0 includes:

- actor and contact point management for sysadmins;
- Scheming selectors, inline creation and record previews;
- latest publisher and three recent contact points per user;
- optional `foaf:Agent` and `vcard:Kind` output through ckanext-dcat;
- optional VCARD telephone serialization for a European DCAT-AP 3 profile.

The extension grew out of a Swedish municipal proof of concept, but the registry
model is intended to be useful across sectors, countries and organization types.
The initial UI is still Swedish-only. It has been manually tested on CKAN 2.11.6
and includes an initial automated suite for registry behavior, access control,
CSRF, dataset projection and RDF serialization. Browser, migration and broader
compatibility testing are still incomplete, so we are explicitly calling this
an alpha release for evaluation rather than a production-ready release.

Before expanding the implementation, we would value feedback on three points:

1. Are you aware of an existing extension that already provides a comparable
   reusable actor and contact point registry?
2. Does the separation between CKAN organization, metadata actor and contact
   point fit your catalog's model?
3. Which API, authorization and multilingual workflows would be most important
   for a 0.2 release?

Repository: REPOSITORY_URL

AI assistance disclosure: the initial implementation and documentation were
developed by Björn Hagström with assistance from OpenAI's ChatGPT and Codex. The
human maintainer reviewed the released work and accepts responsibility for its
correctness, security, licensing and provenance.
