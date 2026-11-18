"""Migrate to Actor Registry, step 1: contact points.

Finds the contact details stored in CKAN's own free-text fields on datasets
that have no registry contact points yet, groups them into candidates (one per
email address, or per name when there is no valid address), and links the
datasets an editor selects to a new or existing contact point.

Rules (see docs/CATALOGUE_SETUPS.md):

- ckanext-dcat's free-text contact point (the repeating field ``contact`` of
  its schemas) is the source when the dataset has one, because ckanext-dcat
  exports it before Maintainer: what is exported is what is migrated. The first
  one is used; a second one is shown as "also mentioned".
- Otherwise Maintainer is the source; Author only when a dataset has no
  Maintainer. When both are set and differ, the author is shown as "also
  mentioned".
- The original fields are never changed. Linking only sets
  ``contact_point_ids``, through ``package_patch``.
- A dataset with registry contact points is done and is not listed.
- Editors see and link only the datasets they may edit; sysadmins all.

Every decision is appended to ``actor_registry_migration_decision``.

A skipped dataset stays skipped while its free-text contact details are the
same (its fingerprint); when they change, it is listed again. Once a dataset
has a contact point, its old fields are hidden in the form as on the page and
in the export, so changes to them no longer need to be followed (0.6.0).
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
# ckanext-dcat's free-text contact point. Kept out of SOURCE_FIELDS: it only
# takes part in a fingerprint when it has a value, so the fingerprints of
# datasets skipped before it was read stay the same.
DCAT_CONTACT_FIELD = "contact"
ALL_SOURCE_FIELDS = SOURCE_FIELDS + (DCAT_CONTACT_FIELD,)
LINKED, SKIPPED, UNSKIPPED, KEPT = "linked", "skipped", "unskipped", "kept"
ACTIONS = ("create", "existing", "skip")


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
        """The source values the decision was made on, or None."""
        try:
            values = json.loads(self.source_values or "null")
        except ValueError:
            return None
        if not isinstance(values, list) or len(values) not in (len(SOURCE_FIELDS), len(ALL_SOURCE_FIELDS)):
            return None
        return _values_dict(values)


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


def _get(row, field):
    return row.get(field) if isinstance(row, dict) else getattr(row, field, None)


def _dcat_entries(value):
    """The stored extra (a JSON list of objects) or an already parsed list, as a list of dicts."""
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else []
        except ValueError:
            return []
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


def _translations(value):
    """A translated subfield (ckanext-fluent, e.g. ``name_translated``) as {language: text}."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    if not isinstance(value, dict):
        return {}
    return {str(lang): clean(text) for lang, text in value.items() if clean(text)}


def _translated_name(entry):
    """``name``, or else the translation in the site's default language, or else the first one."""
    name = clean(entry.get("name"))
    if name:
        return name
    translations = _translations(entry.get("name_translated"))
    default = toolkit.config.get("ckan.locale_default") or "en"
    for lang in [default] + sorted(translations):
        if translations.get(lang):
            return translations[lang]
    return ""


def dcat_contacts(value):
    """ckanext-dcat's free-text contact points as ``[{"name", "email"}]``.

    ``value`` is the stored extra (a JSON list of objects) or an already parsed
    list. A contact point with only a translated name (``name_translated``, as in
    ckanext-dcat's multilingual schema) gets the one in the site's default
    language. Entries without a name and an email are left out; anything that
    is not a list of objects gives ``[]``.
    """
    contacts = []
    for entry in _dcat_entries(value):
        name, email = _translated_name(entry), clean(entry.get("email"))
        if name or email:
            contacts.append({"name": name, "email": email})
    return contacts


def _contacts_text(contacts):
    return "; ".join(
        (item["name"] + (" <%s>" % item["email"] if item["email"] else "")).strip() if item["name"]
        else item["email"] for item in contacts)


def _dcat_text(value):
    """ckanext-dcat's contact points as one text for the page: name, every
    translation of the name ("Desk (en)"), and email."""
    shown = []
    for entry in _dcat_entries(value):
        name = clean(entry.get("name"))
        names = ([name] if name else []) + [
            "%s (%s)" % (text, lang) for lang, text in sorted(_translations(entry.get("name_translated")).items())]
        email = clean(entry.get("email"))
        if names or email:
            shown.append({"name": " / ".join(names), "email": email})
    return _contacts_text(shown) if shown else ""


def source_values(row):
    """The values a dataset's contact details come from, as a list: the four
    Maintainer/Author fields, plus ckanext-dcat's contact points as one text
    when the dataset has any."""
    values = [clean(_get(row, field)) for field in SOURCE_FIELDS]
    dcat_text = _dcat_text(_get(row, DCAT_CONTACT_FIELD))
    if dcat_text:
        values.append(dcat_text)
    return values


def fingerprint(row):
    """A hash of the contact details, to see that they changed after a decision.

    The four Maintainer/Author fields as before; ckanext-dcat's contact points as
    structured values (name, email, every translation of the name), not as the
    text shown, so that "Desk <desk@example.org>" as a name is not the same as
    the name "Desk" with that email. Unchanged for a dataset without them.
    """
    values = [clean(_get(row, field)) for field in SOURCE_FIELDS]
    entries = [[clean(entry.get("name")), clean(entry.get("email")),
                sorted(_translations(entry.get("name_translated")).items())]
               for entry in _dcat_entries(_get(row, DCAT_CONTACT_FIELD))]
    entries = [entry for entry in entries if entry[0] or entry[1] or entry[2]]
    if entries:
        values.append(entries)
    return hashlib.sha256(json.dumps(values).encode("utf-8")).hexdigest()


def contact_source(row):
    """Where a dataset's contact details come from, or None when it has none.

    Returns ``{"source", "name", "email", "email_valid", "raw_email", "also"}``;
    ``source`` is ``contact`` (ckanext-dcat's contact point), ``maintainer``
    or ``author``. ``also`` is a second dcat contact point, or the author when
    it is set next to a different maintainer, as ``{"name", "email"}``.
    """
    contacts = dcat_contacts(_get(row, DCAT_CONTACT_FIELD))
    maintainer = (clean(_get(row, "maintainer")), clean(_get(row, "maintainer_email")))
    author = (clean(_get(row, "author")), clean(_get(row, "author_email")))
    if contacts:
        source, name, raw_email = DCAT_CONTACT_FIELD, contacts[0]["name"], contacts[0]["email"]
        also = dict(contacts[1]) if len(contacts) > 1 else None
    elif any(maintainer):
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
        "author_email, {contacts} AS contact_point_ids, {dcat_contact} AS contact FROM package "
        "WHERE state = 'active' AND type = ANY(:types) "
        "AND (:all_datasets OR owner_org = ANY(:org_ids)) "
        "ORDER BY lower(coalesce(nullif(title, ''), name)), name"
    ).format(contacts=registry_model.extra_text("contact_point_ids"),
             dcat_contact=registry_model.extra_text(DCAT_CONTACT_FIELD))
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
    ``old`` (datasets with contact details in CKAN's fields), ``linked`` (all
    datasets with registry contact points), ``skipped``, ``remaining`` and
    ``no_contact`` (datasets with neither).
    """
    types = migratable_types() if types is None else types
    rows = _scoped_datasets(user, types)
    org_ids = {row.owner_org for row in rows if row.owner_org}
    org_titles = {}
    if org_ids:
        org_titles = {group.id: group.title or group.name for group in
                      ckan_model.Session.query(ckan_model.Group).filter(ckan_model.Group.id.in_(org_ids))}

    counts = {"old": 0, "linked": 0, "skipped": 0, "remaining": 0, "no_contact": 0}
    pending, without_source = [], []
    for row in rows:
        details = contact_source(row)
        has_contact_points = bool(helpers._id_list(row.contact_point_ids))
        if details is None:
            if not has_contact_points:
                counts["no_contact"] += 1
            else:
                without_source.append(row.id)
            continue
        counts["old"] += 1
        details.update({
            "id": row.id, "name_slug": row.name, "title": row.title or row.name,
            "organization": org_titles.get(row.owner_org, ""), "private": bool(row.private),
            "fingerprint": fingerprint(row), "values": _values_dict(source_values(row)),
            "contact_point_ids": helpers._id_list(row.contact_point_ids),
        })
        if has_contact_points:
            counts["linked"] += 1
            continue
        pending.append(details)

    decisions = latest_decisions([item["id"] for item in pending] + without_source)
    # A dataset with a contact point but no free-text details is linked too, whether it got
    # the contact point in the form or through the migration (0.6.0: the overview's "linked"
    # row counts every linked dataset). Linked through the migration but the old value gone
    # since (a schema without the field, and the dataset was saved): still a migrated dataset.
    for package_id in without_source:
        counts["linked"] += 1
        decision = decisions.get(package_id)
        if decision and decision.status in (LINKED, KEPT):
            counts["old"] += 1
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
    return {"types": types, "counts": counts, "candidates": ordered, "skipped": skipped}


def _matches(candidate, contact_points):
    """Existing contact points that look like the candidate: same email, or,
    without an email, the same name."""
    if candidate["email"]:
        return [item for item in contact_points if (item.email or "").lower() == candidate["email"]]
    names = {name.casefold() for name, _count in candidate["names"].items()}
    # A contact point also matches by a name in another language (0.7.0).
    return [item for item in contact_points
            if item.name.casefold() in names or any(row.name.casefold() in names for row in item.translations)]


# --- Applying a decision -----------------------------------------------------------------


class MigrationError(Exception):
    """A decision that cannot be applied at all (nothing was changed)."""


def _values_dict(values):
    """``source_values`` as a dict over ALL_SOURCE_FIELDS ("" for a missing dcat contact)."""
    result = dict.fromkeys(ALL_SOURCE_FIELDS, "")
    result.update(zip(ALL_SOURCE_FIELDS, values))
    return result


def _values_list(values):
    """The inverse of _values_dict: the list ``source_values`` gave."""
    listed = [values.get(field, "") for field in SOURCE_FIELDS]
    if values.get(DCAT_CONTACT_FIELD):
        listed.append(values[DCAT_CONTACT_FIELD])
    return listed


def _record(package_id, status, details, user_id, contact_point_id=None):
    values = details.get("values")
    ckan_model.Session.add(MigrationDecision(
        id=str(uuid.uuid4()), package_id=package_id, status=status, source=details["source"],
        fingerprint=details["fingerprint"], contact_point_id=contact_point_id, user_id=user_id,
        created=datetime.utcnow(),
        source_values=json.dumps(_values_list(values)) if values else None))


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
    values["uri"] = toolkit.url_for("actor_registry.contactpoints_show", item_id=item_id, _external=True, locale="default")
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

    Returns ``{"remaining", "skipped", "no_contact_point", "needs_confirmation"}``;
    ``no_contact_point`` counts every dataset that will have no contact point
    in the DCAT export once the old fields are off.
    """
    counts = survey(user)["counts"]
    no_contact_point = counts["remaining"] + counts["skipped"] + counts["no_contact"]
    return {
        "remaining": counts["remaining"], "skipped": counts["skipped"],
        "no_contact_point": no_contact_point,
        "needs_confirmation": bool(no_contact_point),
    }


def set_closed(user, closed, confirmed=False):
    """Close or reopen the migration (sysadmins only, through CKAN's own
    config_option_update, which checks that). Closing with work left needs
    ``confirmed``. Raises MigrationError or NotAuthorized."""
    if closed and not confirmed and close_check(user)["needs_confirmation"]:
        raise MigrationError(toolkit._(
            "Some datasets still have no contact point. "
            "Confirm that you want to close the migration anyway."))
    toolkit.get_action("config_option_update")(
        {"user": user}, {helpers.LEGACY_CONTACT_FIELDS_OPTION: not closed})
