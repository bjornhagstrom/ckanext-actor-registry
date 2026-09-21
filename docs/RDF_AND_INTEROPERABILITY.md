# RDF and interoperability decisions

## What is reused from the CKAN ecosystem

The extension should not implement a second RDF stack. It reuses
`ckanext-dcat` for DCAT parsing, serialization and endpoints, and
`ckanext-scheming` for field storage and form integration.

Scheming's repeating subfields are useful when every dataset owns an embedded
copy of its contacts. The registry deliberately stores stable IDs instead,
because shared publishers and contacts must be maintainable once. On dataset output,
the IDs are projected into the repeating `publisher` and `contact` structures
expected by ckanext-dcat.

The useful patterns to adopt from surrounding extensions are:

- ckanext-dcat's profile and serializer interfaces;
- Scheming's schema-driven form snippets and validators;
- CKAN Action API plus explicit authorization for future registry integrations;
- ckanext-dcat's SHACL validation approach;
- URI-based matching from harvesters, but only with an explicit reconciliation
  step before imported records enter the shared registry;
- internationalized labels as an optional future capability.

The generic visitor contact-form extension `ckanext-contact` solves a different
problem: sending questions from portal visitors. Its CAPTCHA and email-delivery
features do not belong in this metadata registry.

## RDF model

- A dataset's publisher is connected with `dct:publisher` and represented as a
  FOAF agent. It is the entity responsible for making the dataset available.
- A dataset's contact point is connected with `dcat:contactPoint` and represented
  as `vcard:Kind`. It is contact information, not another publisher role.
- Contact telephone numbers are emitted with `vcard:hasTelephone`,
  `vcard:Voice` and a `vcard:hasValue` `tel:` URI.
- Stable URIs allow several datasets to refer to the same RDF resource.
- Publisher and contact-point URIs must be different, even when a contact belongs to
  the publisher. Using the same URI merges two semantically different resources.

The optional `actor_registry_euro_dcat_ap_3` profile extends ckanext-dcat's
European DCAT-AP 3 profile. Enabling it is not by itself a claim of complete
DCAT-AP-SE conformance; the catalog schema and all other metadata must also be
validated.

Controlled vocabulary values used for dataset themes and publisher types are
typed as `skos:Concept` in the exported graph. Publisher type should therefore
be stored as a concept URI, not a local display label. A validator may still
need the authoritative vocabulary graph to obtain `skos:prefLabel` values.

## Recommended next RDF work

1. Keep export as the first supported direction and verify it with graph and
   SHACL tests.
2. Add read-only Action API endpoints for publishers and contacts if a concrete
   integration needs them, followed by separately authorized create/update actions.
   A full CRUD API is deliberately not planned; see [BACKLOG.md](BACKLOG.md) for why.
3. Add JSON/CSV registry export and reviewed import for operational portability.
4. For RDF harvesting, reconcile by stable URI and show conflicts to an
   administrator. Do not automatically turn every harvested embedded contact
   into a global registry record.
5. Consider additional agent roles and multilingual names only after publisher
   and contact interoperability is stable.
