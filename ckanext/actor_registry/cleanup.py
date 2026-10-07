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
        return sorted(rows, key=lambda entry: ((entry["record"].name.casefold() if entry["record"] else ""),
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
