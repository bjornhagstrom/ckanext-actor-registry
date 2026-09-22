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
  tasks. The browser tests should specifically cover what the current JS unit tests (logic
  only) cannot: Select2 pickers, the inline creation dialogs, preview updates, focus and
  keyboard flows, and both the English and Swedish interfaces.
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
- **A startup test with the plugin disabled.** Start CKAN against a database that already
  has the extension's tables and data, with `actor_registry` removed from `ckan.plugins`,
  and confirm CKAN starts normally and the extension's data is left untouched. Useful before
  telling operators it is safe to turn the extension off temporarily.
- **A documented, tested uninstall path.** What happens when the Python package is removed
  is not currently documented or tested: whether the migration tables and data are expected
  to stay (matching how CKAN extensions usually behave, so that data survives a reinstall)
  or need a separate down-migration/cleanup step.
- **More security testing beyond authorization and CSRF** (both already covered, see
  [TESTING.md](../TESTING.md)): a malformed or unknown UUID in a URL (`/actors/<bad-id>`,
  `/contactpoints/<bad-id>`) should return 404, not a 500 or a stack trace.
- **Load testing** with many publishers, contact points and datasets, in particular the
  registry lists, the worklist and the merge/delete actions (they update every dataset that
  points at the actor being merged or deleted).
- **Visual regression testing** of the registry's own pages and the dataset form, in both
  English and Swedish.

None of these block an alpha release; they matter more the more widely the extension is
used. An AI-assisted review of the 0.2.0 release raised these (see
[AI_ASSISTANCE.md](../AI_ASSISTANCE.md)).

## Known issues

- **CKAN core's own API-token round-trip can fail in a CKAN 2.12 image built on Python
  3.14.** In one development environment (`ckan/ckan-base:2.12`, Python 3.14.7, PyJWT
  2.13.0), any test using CKAN's own `factories.SysadminWithToken()` /
  `factories.UserWithToken()` got HTTP 403 instead of the expected response, because CKAN
  could not verify the JWT it had just issued. This is not caused by this extension: the
  same failure appears against a freshly rebuilt test database, after restarting the
  container, and with every change in this extension reverted; a plain PyJWT encode/decode
  round trip in the same container works correctly in isolation, which points at something
  in CKAN core's own secret handling rather than the underlying library. It was not
  reproduced in the GitHub Actions CI images used for the 0.2.0 release. If you see
  widespread, otherwise-unexplained 403s in your own CKAN 2.12 test runs, check whether your
  base image has moved to Python 3.14 and whether a plain CKAN checkout (no extensions) has
  the same problem; if so, it likely belongs in an upstream CKAN issue rather than here.

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
