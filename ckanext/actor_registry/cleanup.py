"""Clean-up of registry references on datasets.

Lists the inactive publishers and contact points that datasets still use, and
the datasets that point to records that no longer exist, and replaces (or
removes) such a reference on the datasets the user may edit. Editors work on
their own datasets, sysadmins on all; every change goes through
``package_patch``, so the usual permission and schema checks apply.

Stored values are read in Python (``helpers._id_list``), so a broken value on
one dataset cannot break the page.
"""

from ckan import model as ckan_model
from ckan.plugins import toolkit
from sqlalchemy import text

from ckanext.actor_registry import contact_migration, helpers
from ckanext.actor_registry import model as registry_model

KINDS = ("publisher", "contact_point")
REMOVE = "__remove__"


class CleanupError(Exception):
    """A replacement that cannot be made at all (nothing was changed)."""


def _datasets():
    sql = (
        "SELECT id, name, title, owner_org, private, {publisher} AS publisher, "
        "{contacts} AS contacts FROM package WHERE state = 'active' "
        "ORDER BY lower(coalesce(nullif(title, ''), name)), name"
    ).format(publisher=registry_model.extra_text("publisher_actor_id"),
             contacts=registry_model.extra_text("contact_point_ids"))
    return ckan_model.Session.execute(text(sql)).fetchall()


def _entry(store, key, record, kind):
    return store.setdefault(key, {"id": key, "kind": kind, "record": record, "total": 0, "datasets": []})


def survey(user):
    """``{"publishers", "contact_points", "missing"}``: the inactive records in
    use and the references to missing records, each with ``total`` (all
    datasets) and ``datasets`` (the ones ``user`` may edit). Editors only see
    entries that concern at least one of their datasets."""
    all_datasets, org_ids = contact_migration.editable_scope(user)
    org_ids = set(org_ids)
    actors = {item.id: item for item in registry_model.all_actors(include_inactive=True)}
    contacts = {item.id: item for item in registry_model.all_contact_points(include_inactive=True)}
    publishers, contact_points, missing = {}, {}, {}
    for row in _datasets():
        editable = all_datasets or row.owner_org in org_ids
        dataset = {"id": row.id, "name": row.name, "title": row.title or row.name}
        references = []
        publisher_id = (row.publisher or "").strip()
        if publisher_id:
            references.append(("publisher", publisher_id, actors.get(publisher_id)))
        for contact_id in helpers._id_list(row.contacts):
            references.append(("contact_point", contact_id, contacts.get(contact_id)))
        for kind, record_id, record in references:
            if record is None:
                entry = _entry(missing, (kind, record_id), None, kind)
                entry["id"] = record_id
            elif not record.active:
                entry = _entry(publishers if kind == "publisher" else contact_points, record_id, record, kind)
            else:
                continue
            entry["total"] += 1
            if editable:
                entry["datasets"].append(dataset)

    def visible(entries):
        rows = [entry for entry in entries.values() if all_datasets or entry["datasets"]]
        return sorted(rows, key=lambda entry: ((entry["record"].display_name.casefold() if entry["record"] else ""),
                                               entry["kind"], entry["id"]))

    result = {"publishers": visible(publishers), "contact_points": visible(contact_points),
              "missing": visible(missing)}
    for entry in result["publishers"]:
        target = entry["record"].merged_into_id
        merged = actors.get(target) if target else None
        entry["merged_into"] = merged if merged is not None and merged.active else None
    return result


def count(user):
    """How many entries the clean-up page lists for ``user`` (for a hint)."""
    data = survey(user)
    return sum(len(data[key]) for key in ("publishers", "contact_points", "missing"))


def replace(user, kind, old_id, new_id):
    """Replace (or, with ``new_id`` set to ``REMOVE``, remove) the reference ``old_id``
    on the datasets ``user`` may edit. Returns ``(changed, failures)``;
    ``failures`` is a list of ``(dataset title, message)``."""
    if kind not in KINDS:
        raise CleanupError(toolkit._("Unknown kind of reference."))
    new_id = (new_id or "").strip()
    if not new_id:
        raise CleanupError(toolkit._("Choose what to replace it with."))
    if new_id == REMOVE:
        new_id = ""
    if new_id == old_id:
        raise CleanupError(toolkit._("Choose a different record to replace it with."))
    if new_id:
        get = registry_model.get_actor if kind == "publisher" else registry_model.get_contact_point
        new = get(new_id)
        if new is None or not new.active:
            raise CleanupError(toolkit._("Choose an active record to replace it with."))

    data = survey(user)
    entries = data["publishers"] if kind == "publisher" else data["contact_points"]
    entries = entries + [entry for entry in data["missing"] if entry["kind"] == kind]
    entry = next((item for item in entries if item["id"] == old_id), None)
    if entry is None or not entry["datasets"]:
        raise CleanupError(toolkit._("There is nothing to replace on the datasets you may edit."))

    changed, failures = [], []
    for dataset in entry["datasets"]:
        if kind == "publisher":
            patch = {"publisher_actor_id": new_id}
        else:
            current = toolkit.get_action("package_show")({"user": user}, {"id": dataset["id"]})
            ids = [new_id if item == old_id else item for item in helpers._id_list(current.get("contact_point_ids"))]
            patch = {"contact_point_ids": [item for item in dict.fromkeys(ids) if item]}
        try:
            toolkit.get_action("package_patch")({"user": user}, dict(patch, id=dataset["id"]))
        except toolkit.ValidationError as error:
            ckan_model.Session.rollback()
            failures.append((dataset["title"], contact_migration._summary(error)))
            continue
        except toolkit.NotAuthorized:
            ckan_model.Session.rollback()
            failures.append((dataset["title"], toolkit._("You may not edit this dataset.")))
            continue
        changed.append(dataset)
    return changed, failures


def publisher_types():
    """Dataset types whose Scheming schema has the publisher field (``publisher_actor_id``)."""
    try:
        from ckanext.scheming.helpers import scheming_dataset_schemas
        schemas = scheming_dataset_schemas() or {}
    except Exception:  # Scheming not installed or not loaded: no schema has the field.
        return set()
    return {dataset_type for dataset_type, schema in schemas.items()
            if any(field.get("field_name") == "publisher_actor_id" for field in schema.get("dataset_fields", []))}


def field_types():
    """``{"publisher": types, "contact_point": types}``: the dataset types that have each field."""
    return {"publisher": publisher_types(), "contact_point": set(contact_migration.migratable_types())}


def _locked_links(package_id):
    """``(publisher, contact point ids)`` as stored, read with the dataset's row locked until
    the transaction ends."""
    # Lock first, then read in a statement of its own: on CKAN 2.11 the links are in package_extra,
    # and a statement that had to wait for the lock would read them from before the wait.
    ckan_model.Session.execute(text("SELECT id FROM package WHERE id = :id FOR UPDATE"), {"id": package_id})
    sql = "SELECT {publisher} AS publisher, {contacts} AS contacts FROM package WHERE id = :id".format(
        publisher=registry_model.extra_text("publisher_actor_id"), contacts=registry_model.contact_ids_jsonb())
    row = ckan_model.Session.execute(text(sql), {"id": package_id}).first()
    if row is None:
        return "", []
    return (row.publisher or "").strip(), [item for item in (row.contacts or []) if item]


def assign(user, dataset_ids, actor_id="", contact_point_id=""):
    """Set a publisher and/or a contact point on the chosen datasets where it is missing
    (0.6.0, the "To do" list).

    Only what a dataset lacks is set: a dataset that already has a publisher (or a contact
    point) keeps it and is counted in ``skipped``, so a stale page can never overwrite one.
    A dataset whose type has no such field is reported in ``failures``. Every change goes
    through ``package_patch`` as ``user``. Returns ``{"actor", "contact_point", "changed",
    "skipped", "failures"}``: ``changed`` and ``skipped`` are ``{"publisher": [...],
    "contact_point": [...]}`` lists of datasets, ``failures`` a list of ``(title, message)``."""
    actor_id, contact_point_id = (actor_id or "").strip(), (contact_point_id or "").strip()
    if not actor_id and not contact_point_id:
        raise CleanupError(toolkit._("Choose a publisher or a contact point."))
    actor = registry_model.get_actor(actor_id) if actor_id else None
    if actor_id and (actor is None or not actor.active):
        raise CleanupError(toolkit._("Choose an active publisher."))
    contact_point = registry_model.get_contact_point(contact_point_id) if contact_point_id else None
    if contact_point_id and (contact_point is None or not contact_point.active):
        raise CleanupError(toolkit._("Choose an active contact point."))
    dataset_ids = [item for item in dict.fromkeys(dataset_ids or []) if item]
    if not dataset_ids:
        raise CleanupError(toolkit._("Select at least one dataset."))

    types = field_types()
    wanted = [kind for kind, record in (("publisher", actor), ("contact_point", contact_point)) if record]
    no_field = {"publisher": toolkit._("This kind of dataset has no publisher field."),
                "contact_point": toolkit._("This kind of dataset has no contact point field.")}
    result = {"actor": actor, "contact_point": contact_point, "failures": [],
              "changed": {"publisher": [], "contact_point": []}, "skipped": {"publisher": [], "contact_point": []}}
    for dataset_id in dataset_ids:
        try:
            current = toolkit.get_action("package_show")({"user": user}, {"id": dataset_id})
        except (toolkit.ObjectNotFound, toolkit.NotAuthorized):
            result["failures"].append((dataset_id, toolkit._("The dataset was not found.")))
            continue
        dataset = {"id": current["id"], "name": current.get("name"),
                   "title": current.get("title") or current.get("name") or dataset_id}
        kinds = [kind for kind in wanted if current.get("type") in types[kind]]
        for kind in wanted:
            if kind not in kinds:
                result["failures"].append((dataset["title"], no_field[kind]))
        if not kinds:
            continue
        # Lock the dataset's row and read its links from the database under the lock, so that a
        # publisher or contact point another editor saves meanwhile is never overwritten: their save
        # waits until package_patch below commits (which releases the lock), or it came first and is seen here.
        publisher, contacts = _locked_links(current["id"])
        patch = {}
        for kind in kinds:
            if (publisher if kind == "publisher" else contacts):
                result["skipped"][kind].append(dataset)
            elif kind == "publisher":
                patch["publisher_actor_id"] = actor.id
            else:
                patch["contact_point_ids"] = [contact_point.id]
        if not patch:
            ckan_model.Session.rollback()
            continue
        try:
            toolkit.get_action("package_patch")({"user": user}, dict(patch, id=current["id"]))
        except toolkit.ValidationError as error:
            ckan_model.Session.rollback()
            result["failures"].append((dataset["title"], contact_migration._summary(error)))
            continue
        except toolkit.NotAuthorized:
            ckan_model.Session.rollback()
            result["failures"].append((dataset["title"], toolkit._("You may not edit this dataset.")))
            continue
        for kind, field_name in (("publisher", "publisher_actor_id"), ("contact_point", "contact_point_ids")):
            if field_name in patch:
                result["changed"][kind].append(dataset)
    return result
