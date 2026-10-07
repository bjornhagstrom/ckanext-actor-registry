"""Migrate to Actor Registry, step 1: contact points.

Finds the contact details stored in CKAN's own free-text fields on datasets
that have no registry contact points yet, groups them into candidates (one per
email address, or per name when there is no valid address), and links the
datasets an editor selects to a new or existing contact point.

Rules (see docs/CATALOGUE_SETUPS.md):

- Maintainer is the source; Author only when a dataset has no Maintainer. When
  both are set and differ, the author is shown as "also mentioned".
- The original fields are never changed. Linking only sets
  ``contact_point_ids``, through ``package_patch``.
- A dataset with registry contact points is done and is not listed.
- Editors see and link only the datasets they may edit; sysadmins all.

Every decision is appended to ``actor_registry_migration_decision``.

Step 2, changes in the source: when Maintainer or Author changes on a linked
dataset, its fingerprint no longer matches the decision, and the dataset is
listed as "changed since linking". The editor updates the contact point, links
another one, or keeps it as it is; each choice is a new decision with the new
fingerprint.
"""

import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime

from ckan import authz
from ckan import model as ckan_model
from ckan.plugins import toolkit
from sqlalchemy import Column, DateTime, String, Text, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, TEXT as PG_TEXT

from ckanext.actor_registry import helpers, validation
from ckanext.actor_registry import model as registry_model

SOURCE_FIELDS = ("maintainer", "maintainer_email", "author", "author_email")
LINKED, SKIPPED, UNSKIPPED, KEPT = "linked", "skipped", "unskipped", "kept"
ACTIONS = ("create", "existing", "skip")
CHANGE_ACTIONS = ("update", "existing", "create", "keep")


class MigrationDecision(toolkit.BaseModel):
    __tablename__ = "actor_registry_migration_decision"

    id = Column(String(36), primary_key=True)
    package_id = Column(String(36), nullable=False)
    status = Column(String(20), nullable=False)
    source = Column(String(20), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    contact_point_id = Column(String(36), nullable=True)
    user_id = Column(String(36), nullable=True)
    created = Column(DateTime, nullable=False, default=datetime.utcnow)
    source_values = Column(Text, nullable=True)

    def values(self):
        """The Maintainer/Author values the decision was made on, or None."""
        try:
            values = json.loads(self.source_values or "null")
        except ValueError:
            return None
        return dict(zip(SOURCE_FIELDS, values)) if isinstance(values, list) and len(values) == 4 else None


# --- Normalising the free-text fields --------------------------------------------------


def clean(value):
    """Trimmed text with every run of whitespace collapsed to one space."""
    return " ".join(str(value or "").split())


def normalise_email(value):
    """``(address, is_valid)``: the lowercased address and whether it is usable."""
    address = clean(value).lower()
    if not address:
        return "", False
    try:
        validation.valid_email(address, {})
    except toolkit.Invalid:
        return address, False
    return address, True


def source_values(row):
    return [clean(getattr(row, field, None) if not isinstance(row, dict) else row.get(field))
            for field in SOURCE_FIELDS]


def fingerprint(row):
    return hashlib.sha256(json.dumps(source_values(row)).encode("utf-8")).hexdigest()


def contact_source(row):
    """Where a dataset's contact details come from, or None when it has none.

    Returns ``{"source", "name", "email", "email_valid", "raw_email", "also"}``;
    ``also`` is the author as ``{"name", "email"}`` when it is set next to a
    different maintainer.
    """
    get = (lambda field: row.get(field)) if isinstance(row, dict) else (lambda field: getattr(row, field, None))
    maintainer = (clean(get("maintainer")), clean(get("maintainer_email")))
    author = (clean(get("author")), clean(get("author_email")))
    if any(maintainer):
        source, (name, raw_email) = "maintainer", maintainer
        also = None
        if any(author) and (author[0].casefold(), author[1].lower()) != (name.casefold(), raw_email.lower()):
            also = {"name": author[0], "email": author[1]}
    elif any(author):
        source, (name, raw_email), also = "author", author, None
    else:
        return None
    email, email_valid = normalise_email(raw_email)
    return {"source": source, "name": name, "email": email if email_valid else "",
            "email_valid": email_valid, "raw_email": raw_email, "also": also}


def candidate_key(details):
    if details["email_valid"]:
        return "email:" + details["email"]
    return "name:" + (details["name"] or details["raw_email"]).casefold()


# --- Who may migrate what ---------------------------------------------------------------


def editable_scope(user):
    """``(all_datasets, organization_ids)`` the user may edit, for the migration."""
    if not user:
        return False, []
    if authz.is_sysadmin(user):
        return True, []
    try:
        orgs = toolkit.get_action("organization_list_for_user")(
            {"user": user}, {"permission": "update_dataset"})
    except toolkit.NotAuthorized:
        orgs = []
    return False, [org["id"] for org in orgs]


def can_migrate(user):
    all_datasets, org_ids = editable_scope(user)
    return all_datasets or bool(org_ids)


def migratable_types():
    """Dataset types whose Scheming schema has the contact points field."""
    try:
        from ckanext.scheming.helpers import scheming_dataset_schemas
        schemas = scheming_dataset_schemas() or {}
    except Exception:  # Scheming not installed or not loaded: no schema has the field.
        return []
    return sorted(
        dataset_type for dataset_type, schema in schemas.items()
        if any(field.get("field_name") == "contact_point_ids"
               for field in schema.get("dataset_fields", []))
    )


# --- Survey: what is done, skipped and remaining ---------------------------------------


def _scoped_datasets(user, types):
    all_datasets, org_ids = editable_scope(user)
    if not types or not (all_datasets or org_ids):
        return []
    sql = (
        "SELECT id, name, title, owner_org, private, maintainer, maintainer_email, author, "
        "author_email, {contacts} AS contact_point_ids FROM package "
        "WHERE state = 'active' AND type = ANY(:types) "
        "AND (:all_datasets OR owner_org = ANY(:org_ids)) "
        "ORDER BY lower(coalesce(nullif(title, ''), name)), name"
    ).format(contacts=registry_model.extra_text("contact_point_ids"))
    array = ARRAY(PG_TEXT)
    statement = text(sql).bindparams(bindparam("types", type_=array), bindparam("org_ids", type_=array))
    return ckan_model.Session.execute(
        statement, {"types": list(types), "all_datasets": bool(all_datasets),
                    "org_ids": [str(item) for item in org_ids]},
    ).fetchall()


def latest_decisions(package_ids):
    if not package_ids:
        return {}
    latest = {}
    query = (ckan_model.Session.query(MigrationDecision)
             .filter(MigrationDecision.package_id.in_(list(package_ids)))
             .order_by(MigrationDecision.created))
    for decision in query:
        latest[decision.package_id] = decision
    return latest


def survey(user, types=None):
    """Everything the migration page shows, for ``user``'s datasets.

    Returns ``{"types", "counts", "candidates", "skipped"}``. ``counts`` has
    ``old`` (datasets with contact details in CKAN's fields), ``linked`` (of
    those, the ones with registry contact points), ``skipped``, ``remaining``
    and ``no_contact`` (datasets with neither).
    """
    types = migratable_types() if types is None else types
    rows = _scoped_datasets(user, types)
    org_ids = {row.owner_org for row in rows if row.owner_org}
    org_titles = {}
    if org_ids:
        org_titles = {group.id: group.title or group.name for group in
                      ckan_model.Session.query(ckan_model.Group).filter(ckan_model.Group.id.in_(org_ids))}

    counts = {"old": 0, "linked": 0, "skipped": 0, "remaining": 0, "no_contact": 0, "changed": 0}
    pending, linked_rows = [], []
    for row in rows:
        details = contact_source(row)
        has_contact_points = bool(helpers._id_list(row.contact_point_ids))
        if details is None:
            if not has_contact_points:
                counts["no_contact"] += 1
            continue
        counts["old"] += 1
        details.update({
            "id": row.id, "name_slug": row.name, "title": row.title or row.name,
            "organization": org_titles.get(row.owner_org, ""), "private": bool(row.private),
            "fingerprint": fingerprint(row), "values": dict(zip(SOURCE_FIELDS, source_values(row))),
            "contact_point_ids": helpers._id_list(row.contact_point_ids),
        })
        if has_contact_points:
            counts["linked"] += 1
            linked_rows.append(details)
            continue
        pending.append(details)

    decisions = latest_decisions([item["id"] for item in pending + linked_rows])
    changed = []
    for item in linked_rows:
        decision = decisions.get(item["id"])
        if decision and decision.status in (LINKED, KEPT) and decision.fingerprint != item["fingerprint"]:
            item["decision"] = decision
            item["previous"] = decision.values()
            contact = registry_model.get_contact_point(decision.contact_point_id) if decision.contact_point_id else None
            item["contact_point"] = contact
            item["contact_point_in_dataset"] = bool(contact) and contact.id in item["contact_point_ids"]
            changed.append(item)
    counts["changed"] = len(changed)
    if changed:
        usage = contact_point_usage()
        for item in changed:
            item["usage"] = usage.get(item["contact_point"].id, 0) if item["contact_point"] else 0
    candidates, skipped = {}, []
    for item in pending:
        decision = decisions.get(item["id"])
        if decision and decision.status == SKIPPED and decision.fingerprint == item["fingerprint"]:
            counts["skipped"] += 1
            skipped.append(item)
            continue
        counts["remaining"] += 1
        key = candidate_key(item)
        candidate = candidates.setdefault(key, {
            "key": key, "email": item["email"], "names": Counter(), "invalid_emails": set(),
            "datasets": [],
        })
        if item["name"]:
            candidate["names"][item["name"]] += 1
        if item["raw_email"] and not item["email_valid"]:
            candidate["invalid_emails"].add(item["raw_email"])
        candidate["datasets"].append(item)

    contact_points = registry_model.all_contact_points()
    for candidate in candidates.values():
        names = sorted(candidate["names"].items(), key=lambda pair: (-pair[1], pair[0].casefold()))
        candidate["variants"] = names
        candidate["suggested_name"] = (names[0][0] if names else "") or candidate["email"] or next(
            iter(sorted(candidate["invalid_emails"])), "")
        candidate["invalid_emails"] = sorted(candidate["invalid_emails"])
        candidate["matches"] = _matches(candidate, contact_points)
        candidate["also"] = [item for item in candidate["datasets"] if item["also"]]
    ordered = sorted(candidates.values(),
                     key=lambda c: (-len(c["datasets"]), c["suggested_name"].casefold(), c["key"]))
    return {"types": types, "counts": counts, "candidates": ordered, "skipped": skipped,
            "changed": changed}


def contact_point_usage():
    """How many active datasets list each contact point. Parsed in Python, so a
    dataset with a broken stored value cannot break the count."""
    rows = ckan_model.Session.execute(text(
        "SELECT {contacts} AS contact_point_ids FROM package WHERE state = 'active'".format(
            contacts=registry_model.extra_text("contact_point_ids"))))
    usage = Counter()
    for row in rows:
        usage.update(set(helpers._id_list(row.contact_point_ids)))
    return usage


def _matches(candidate, contact_points):
    """Existing contact points that look like the candidate: same email, or,
    without an email, the same name."""
    if candidate["email"]:
        return [item for item in contact_points if (item.email or "").lower() == candidate["email"]]
    names = {name.casefold() for name, _count in candidate["names"].items()}
    return [item for item in contact_points if item.name.casefold() in names]


# --- Applying a decision -----------------------------------------------------------------


class MigrationError(Exception):
    """A decision that cannot be applied at all (nothing was changed)."""


def _record(package_id, status, details, user_id, contact_point_id=None):
    values = details.get("values")
    ckan_model.Session.add(MigrationDecision(
        id=str(uuid.uuid4()), package_id=package_id, status=status, source=details["source"],
        fingerprint=details["fingerprint"], contact_point_id=contact_point_id, user_id=user_id,
        created=datetime.utcnow(),
        source_values=json.dumps([values[field] for field in SOURCE_FIELDS]) if values else None))


def _user_id(user):
    user_obj = ckan_model.User.get(user)
    return user_obj.id if user_obj else None


def _new_contact_point(name, email):
    """A validated, saved new contact point (raises MigrationError)."""
    values = {"name": clean(name), "email": clean(email), "phone": "", "url": "",
              "actor_id": None, "active": True}
    if not values["name"]:
        raise MigrationError(toolkit._("Name or role is required."))
    item_id = str(uuid.uuid4())
    values["uri"] = toolkit.url_for("actor_registry.contactpoints_show", item_id=item_id, _external=True)
    error = validation.contact_point_error(values)
    if error:
        raise MigrationError(error)
    contact_point = registry_model.ContactPoint(id=item_id, **values)
    ckan_model.Session.add(contact_point)
    ckan_model.Session.commit()
    return contact_point


def apply(user, action, dataset_ids, name="", email="", contact_point_id="", group_key="", exclude_ids=()):
    """Apply one decision to the selected datasets of a candidate.

    A large candidate is posted as ``group_key`` plus the few datasets to leave out
    (``exclude_ids``), not as one id per dataset: a form with a thousand fields is refused
    by the web framework. ``dataset_ids`` is then ignored.

    Only datasets that are still remaining for ``user`` are touched, whatever
    ids are posted. Returns ``(linked_or_skipped, failures, contact_point)``;
    ``failures`` is a list of ``(dataset title, message)``. Raises
    ``MigrationError`` when nothing could be done.
    """
    if action not in ACTIONS:
        raise MigrationError(toolkit._("Choose what to do with the selected datasets."))
    candidates = survey(user)["candidates"]
    remaining = {item["id"]: item for candidate in candidates for item in candidate["datasets"]}
    if group_key:
        left_out = set(exclude_ids or [])
        group = next((candidate for candidate in candidates if candidate["key"] == group_key), None)
        dataset_ids = [item["id"] for item in group["datasets"] if item["id"] not in left_out] if group else []
    selected = [remaining[package_id] for package_id in dict.fromkeys(dataset_ids or [])
                if package_id in remaining]
    if not selected:
        raise MigrationError(toolkit._("Select at least one dataset that still needs a contact point."))
    user_id = _user_id(user)

    if action == "skip":
        for item in selected:
            _record(item["id"], SKIPPED, item, user_id)
        ckan_model.Session.commit()
        return selected, [], None

    created = False
    if action == "existing":
        contact_point = _active_contact_point(contact_point_id)
    else:
        contact_point = _new_contact_point(name, email)
        created = True

    linked, failures = [], []
    for item in selected:
        try:
            toolkit.get_action("package_patch")(
                {"user": user}, {"id": item["id"], "contact_point_ids": [contact_point.id]})
        except toolkit.ValidationError as error:
            ckan_model.Session.rollback()
            failures.append((item["title"], _summary(error)))
            continue
        except toolkit.NotAuthorized:
            ckan_model.Session.rollback()
            failures.append((item["title"], toolkit._("You may not edit this dataset.")))
            continue
        _record(item["id"], LINKED, item, user_id, contact_point.id)
        ckan_model.Session.commit()
        linked.append(item)

    if created and not linked:
        # Nothing uses the new contact point: do not leave an orphan behind.
        ckan_model.Session.delete(contact_point)
        ckan_model.Session.commit()
        contact_point = None
    return linked, failures, contact_point


def _active_contact_point(contact_point_id):
    contact_point = registry_model.get_contact_point(contact_point_id) if contact_point_id else None
    if not contact_point or not contact_point.active:
        raise MigrationError(toolkit._("Choose an active contact point."))
    return contact_point


def resolve_change(user, package_id, action, name="", email="", contact_point_id=""):
    """Decide what to do with a linked dataset whose Maintainer/Author changed.

    ``update`` changes the linked contact point itself (for every dataset
    that uses it), ``existing``/``create`` puts another contact point in its
    place on this dataset only, and ``keep`` accepts the change as it is.
    Returns the contact point in use afterwards (None for ``keep``). Raises
    ``MigrationError`` when nothing was changed.
    """
    if action not in CHANGE_ACTIONS:
        raise MigrationError(toolkit._("Choose what to do with the change."))
    item = next((entry for entry in survey(user)["changed"] if entry["id"] == package_id), None)
    if item is None:
        raise MigrationError(toolkit._("The dataset is no longer among the changed ones."))
    user_id = _user_id(user)
    old = item["contact_point"]

    if action == "keep":
        _record(item["id"], KEPT, item, user_id, old.id if old else None)
        ckan_model.Session.commit()
        return None

    if action == "update":
        if not old or not old.active or not item["contact_point_in_dataset"]:
            raise MigrationError(toolkit._(
                "The contact point it was linked to is no longer in use on this dataset. "
                "Link another one instead."))
        values = {"name": clean(name), "email": clean(email)}
        if not values["name"]:
            raise MigrationError(toolkit._("Name or role is required."))
        error = validation.contact_point_error(values, existing=old)
        if error:
            raise MigrationError(error)
        old.name, old.email = values["name"], values["email"] or None
        ckan_model.Session.commit()
        _record(item["id"], LINKED, item, user_id, old.id)
        ckan_model.Session.commit()
        return old

    if action == "existing":
        new = _active_contact_point(contact_point_id)
        created = False
    else:
        new = _new_contact_point(name, email)
        created = True
    ids = item["contact_point_ids"]
    if old and old.id in ids:
        ids = [new.id if contact_id == old.id else contact_id for contact_id in ids]
    else:
        ids = ids + [new.id]
    try:
        toolkit.get_action("package_patch")(
            {"user": user}, {"id": item["id"], "contact_point_ids": list(dict.fromkeys(ids))})
    except (toolkit.ValidationError, toolkit.NotAuthorized) as error:
        ckan_model.Session.rollback()
        if created:
            ckan_model.Session.delete(new)
            ckan_model.Session.commit()
        message = _summary(error) if isinstance(error, toolkit.ValidationError) else toolkit._(
            "You may not edit this dataset.")
        raise MigrationError(toolkit._("Could not link {title}: {message}").format(
            title=item["title"], message=message))
    _record(item["id"], LINKED, item, user_id, new.id)
    ckan_model.Session.commit()
    return new


def _summary(error):
    summary = getattr(error, "error_summary", None) or {}
    if isinstance(summary, dict):
        return "; ".join("{0}: {1}".format(key, value) for key, value in summary.items()) or str(error)
    return str(summary)


def unskip(user, package_id):
    """Put a skipped dataset back among the remaining ones. Returns True if it was skipped."""
    skipped = {item["id"]: item for item in survey(user)["skipped"]}
    item = skipped.get(package_id)
    if not item:
        return False
    _record(package_id, UNSKIPPED, item, _user_id(user))
    ckan_model.Session.commit()
    return True



# --- Step 3: closing (and reopening) the migration ---------------------------------------


def is_closed():
    return not helpers.legacy_contact_fields_in_use()


def close_check(user):
    """What is left before closing, for ``user`` (a sysadmin sees everything).

    Returns ``{"remaining", "changed", "skipped", "no_contact_point", "needs_confirmation"}``;
    ``no_contact_point`` counts every dataset that will have no contact point
    in the DCAT export once the old fields are off.
    """
    counts = survey(user)["counts"]
    no_contact_point = counts["remaining"] + counts["skipped"] + counts["no_contact"]
    return {
        "remaining": counts["remaining"], "changed": counts["changed"], "skipped": counts["skipped"],
        "no_contact_point": no_contact_point,
        "needs_confirmation": bool(no_contact_point or counts["changed"]),
    }


def set_closed(user, closed, confirmed=False):
    """Close or reopen the migration (sysadmins only, through CKAN's own
    config_option_update, which checks that). Closing with work left needs
    ``confirmed``. Raises MigrationError or NotAuthorized."""
    if closed and not confirmed and close_check(user)["needs_confirmation"]:
        raise MigrationError(toolkit._(
            "Some datasets still have no contact point or have unhandled changes. "
            "Confirm that you want to close the migration anyway."))
    toolkit.get_action("config_option_update")(
        {"user": user}, {helpers.LEGACY_CONTACT_FIELDS_OPTION: not closed})
