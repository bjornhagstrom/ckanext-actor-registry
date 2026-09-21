# Backlog

Improvements that are decided but not scheduled, and design choices that are deliberate and
should not be mistaken for gaps. Please open an issue before starting work on any of them.

## Planned

- **Import and export command for registry data** (CSV or JSON). Useful for bulk editing,
  migration and backup outside the database. It should work directly against the model, for
  example as a `ckan` command or a stand-alone script, and **not** on top of a general Action
  API (see below).
- **Browser-based (end-to-end) tests and a formal security review** before the extension is
  used more widely than a pilot. Neither is a code change in itself, but both are concrete
  tasks.
- **Dataset collaborators in the registry lists.** The dataset lists on publisher and contact
  point pages show a private dataset only to sysadmins and to members of the dataset's
  organization. A user who can see a private dataset only as a CKAN *dataset collaborator*
  (`ckan.auth.allow_dataset_collaborators`, off by default) does not see it there. That errs on
  the safe side (too little is shown, nothing leaks). The fix is one more condition in the same
  SQL that already filters visibility (`model.linked_datasets`): include a dataset when
  `id IN (SELECT package_id FROM package_member WHERE user_id = :user)`, only when the feature
  is enabled. It needs a test with a collaborator who is not an organization member, and
  `_viewer_visibility()` in `views.py` must also return the user's id.
- **The worklist on the contact points page.** The *Publishers* page (`/actors`) has a worklist
  of datasets that are missing a publisher and/or a contact point, with a *Missing:* choice
  (both, publisher, contact point, either). The contact points page has no entry point to it;
  linking to `/actors?missing=contact_point` from there, or showing the same list, would make
  the "datasets without a contact point" view easier to find. The list logic is shared
  (`model.linked_datasets`), so the change is in the templates.
- **Screenshots and a short walkthrough** for the README (the image links are in place and
  marked "to be added").

## Deliberate design choices (not gaps)

- **No full `ckan.logic.action` CRUD API for registry management** (create, read, update and
  delete publishers and contact points programmatically). Comparable CKAN registry and metadata
  extensions rarely provide one, and it is not needed for how this extension is used: the
  admin interface covers day-to-day editing, and the merge and delete actions cover the cases
  where a programmatic call has been needed. All validation lives in one shared layer
  (`validation.py`), so an API added later would reuse it rather than duplicate it. Raise an
  issue if you think this should be revisited.
- **Identifier schemes and publisher-type vocabularies are left to the deploying catalog.**
  The extension is meant to be general and portable, so it does not hard-code a vocabulary.
  A catalog that wants to define and validate its own schemes and types does so in its own
  schema and configuration.

## Done

- A finer permission model: the registry (view, create, edit, quick-create) is available to all
  logged-in editors; merging and permanent deletion stay sysadmin-only.
- Automated tests on more than one CKAN release: the suite runs on CKAN 2.11.1, the newest 2.11
  patch and 2.12 (see [TESTING.md](../TESTING.md)).
- The datasets-missing-something worklist, including the choice between missing both, only the
  publisher, only the contact point, or either.
