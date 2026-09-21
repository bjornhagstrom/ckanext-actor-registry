import uuid

from ckan import authz
from ckan.lib.helpers import Page
from ckan import model as ckan_model
from ckan.plugins import toolkit
from flask import Blueprint, abort, g, jsonify, redirect, request
from sqlalchemy.exc import IntegrityError

from ckanext.actor_registry import model as registry_model
from ckanext.actor_registry import validation
from ckanext.actor_registry.actions import MERGEABLE_FIELDS
from ckanext.actor_registry.model import Actor, ContactPoint, all_actors, all_contact_points, get_actor, get_contact_point

MERGE_FIELD_LABELS = {
    "name": "Name",
    "actor_kind": "Kind",
    "actor_type": "Type",
    "identifier": "Identifier",
    "identifier_scheme": "Identifier scheme",
    "url": "URL",
    "email": "Email",
    "description": "Description",
}


def _merge_field_labels():
    # Translated lazily, at request time -- see the note in
    # claude/i18n-plan.md-derived work: a module-level dict built at
    # import time would bake in whatever locale happened to be active
    # when the app first loaded the module, not the current visitor's.
    return {key: toolkit._(value) for key, value in MERGE_FIELD_LABELS.items()}


blueprint = Blueprint("actor_registry", __name__)


def _require_sysadmin():
    try:
        toolkit.check_access("sysadmin", {})
    except toolkit.NotAuthorized:
        abort(403)

def _require_login():
    # 2026-09-16, Björns beslut: aktörs-/kontaktpunktsregistret ska vara
    # fullt tillgängligt för vanliga redaktörer, inte bara sysadmins --
    # registret är inte organisationsscopat så det finns ingen
    # package_update-liknande kontroll att hänga upp detta på istället;
    # "inloggad, inte gäst" är rätt nivå här eftersom självregistrering
    # är avstängd (se require_portal_login i ckanext-skelleftea) -- varje
    # konto som finns är redan manuellt skapat av en sysadmin.
    # Sammanslagningsfunktionen (actors_merge) är explicit UNDANTAGEN --
    # den förblir sysadmin-only (se _require_sysadmin ovan) eftersom den
    # är destruktiv och påverkar datamängder över hela katalogen, inte
    # bara redaktörens egen organisation.
    if not g.user or g.user == "guest":
        abort(403)



def _commit(item, duplicate_message):
    try:
        ckan_model.Session.add(item)
        ckan_model.Session.commit()
        return True
    except IntegrityError:
        ckan_model.Session.rollback()
        toolkit.h.flash_error(duplicate_message)
        return False


def _registry_uri_conflict(uri, item=None):
    return registry_model.registry_uri_owner(
        uri,
        exclude_actor_id=item.id if isinstance(item, Actor) else None,
        exclude_contact_point_id=item.id if isinstance(item, ContactPoint) else None,
    )


def _actor_error(values, item=None):
    """First validation error for an actor's values (normalises them in place), or None.

    The rules live in ``validation`` and are shared with the merge action.
    """
    return validation.actor_error(values, item)


def _contact_error(values, item=None):
    """First validation error for a contact point's values (normalises in place), or None."""
    return validation.contact_point_error(values, item)


def _integrity_message(values, item, fallback):
    """After an IntegrityError rollback, explain an identifier race precisely."""
    return validation.identifier_error(
        values["identifier_scheme"], values["identifier"], values["active"],
        exclude_ids=[item.id] if item is not None else (),
    ) or fallback


def _contact_values(item=None):
    return {
        "name": request.form.get("name", getattr(item, "name", "")).strip(),
        "actor_id": request.form.get("actor_id", getattr(item, "actor_id", "") or "").strip() or None,
        "email": request.form.get("email", getattr(item, "email", "") or "").strip(),
        "phone": request.form.get("phone", getattr(item, "phone", "") or "").strip(),
        "url": request.form.get("url", getattr(item, "url", "") or "").strip(),
        "uri": request.form.get("uri", getattr(item, "uri", "") or "").strip()
        or (getattr(item, "uri", "") if item else ""),
        "active": request.form.get("active", "") == "on",
    }


def _actor_values(item=None):
    return {
        "name": request.form.get("name", getattr(item, "name", "")).strip(),
        "actor_kind": request.form.get("actor_kind", getattr(item, "actor_kind", "organization")).strip(),
        "actor_type": request.form.get("actor_type", getattr(item, "actor_type", "") or "").strip(),
        "identifier": request.form.get("identifier", getattr(item, "identifier", "") or "").strip(),
        "identifier_scheme": request.form.get("identifier_scheme", getattr(item, "identifier_scheme", "") or "").strip(),
        "uri": request.form.get("uri", getattr(item, "uri", "") or "").strip()
        or (getattr(item, "uri", "") if item else ""),
        "url": request.form.get("url", getattr(item, "url", "") or "").strip(),
        "email": request.form.get("email", getattr(item, "email", "") or "").strip(),
        "description": request.form.get("description", getattr(item, "description", "") or "").strip(),
        "active": request.form.get("active", "") == "on",
    }

PREVIEW_SIZE = 10
LIST_PAGE_SIZE = 20


def _viewer_visibility():
    """``(is_sysadmin, organisation_ids)`` deciding which private datasets the
    current visitor may see in registry dataset lists."""
    user = g.user
    if not user:
        return False, []
    if authz.is_sysadmin(user):
        return True, []
    try:
        orgs = toolkit.get_action("organization_list_for_user")(
            {"user": user}, {"permission": "read"}
        )
    except toolkit.NotAuthorized:
        orgs = []
    return False, [org["id"] for org in orgs]


def _linked_datasets(link, subject_ids, page=1, per_page=PREVIEW_SIZE):
    is_sysadmin, org_ids = _viewer_visibility()
    rows, total = registry_model.linked_datasets(
        link, subject_ids, is_sysadmin=is_sysadmin, org_ids=org_ids, page=page, per_page=per_page
    )
    return {"rows": rows, "total": total}


def _page_number():
    try:
        return max(int(request.args.get("page", 1)), 1)
    except ValueError:
        return 1


def _dataset_pager(endpoint, page, total, **url_args):
    return Page(
        collection=[],
        page=page,
        url=lambda **kw: toolkit.url_for(endpoint, **dict(url_args, **kw)),
        item_count=total,
        items_per_page=LIST_PAGE_SIZE,
    )


@blueprint.route("/contactpoints")
def contactpoints_index():
    _require_login()
    # 2026-09-19, samma beslut/mönster som för actors_index: inaktiva
    # kontaktpunkter döljs som standard, en kryssruta visar dem igen.
    show_inactive = request.args.get("show_inactive") == "1"
    return toolkit.render(
        "actor_registry/contactpoints_index.html",
        extra_vars={"items": all_contact_points(show_inactive), "show_inactive": show_inactive},
    )


@blueprint.route("/contactpoints/new", methods=["GET", "POST"])
def contactpoints_new():
    _require_login()
    values = _contact_values()
    if request.method == "POST" and values["name"]:
        item_id = str(uuid.uuid4())
        values["uri"] = values["uri"] or toolkit.url_for("actor_registry.contactpoints_show", item_id=item_id, _external=True)
        field_error = _contact_error(values)
        if field_error:
            toolkit.h.flash_error(field_error)
        elif _registry_uri_conflict(values["uri"]):
            toolkit.h.flash_error(toolkit._("The URI is already used by a publisher or contact point."))
        elif _commit(ContactPoint(id=item_id, **values), toolkit._("The URI is already used by a contact point.")):
            toolkit.h.flash_success(toolkit._("The contact point has been created."))
            return redirect(toolkit.url_for("actor_registry.contactpoints_index"))
    elif request.method == "POST":
        toolkit.h.flash_error(toolkit._("Name or role is required."))
    return toolkit.render("actor_registry/contactpoint_form.html", extra_vars={"item": values, "actors": all_actors(), "is_new": True})


@blueprint.route("/contactpoints/quick-create", methods=["POST"])
def contactpoints_quick_create():
    _require_login()
    values = _contact_values()
    if not values["name"]:
        return jsonify({"success": False, "error": toolkit._("Name or role is required.")}), 400
    item_id = str(uuid.uuid4())
    values["uri"] = values["uri"] or toolkit.url_for("actor_registry.contactpoints_show", item_id=item_id, _external=True)
    values["active"] = True
    field_error = _contact_error(values)
    if field_error:
        return jsonify({"success": False, "error": field_error}), 409
    if _registry_uri_conflict(values["uri"]):
        return jsonify({"success": False, "error": toolkit._("The URI is already used by a publisher or contact point.")}), 409
    item = ContactPoint(id=item_id, **values)
    try:
        ckan_model.Session.add(item)
        ckan_model.Session.commit()
    except IntegrityError:
        ckan_model.Session.rollback()
        return jsonify({"success": False, "error": toolkit._("The URI is already in use.")}), 409
    return jsonify({"success": True, "contact_point": item.as_dict()})


@blueprint.route("/contactpoints/<item_id>/quick-edit", methods=["POST"])
def contactpoints_quick_edit(item_id):
    _require_login()
    item = get_contact_point(item_id)
    if not item:
        return jsonify({"success": False, "error": toolkit._("The contact point was not found.")}), 404
    values = _contact_values(item)
    if not values["name"]:
        return jsonify({"success": False, "error": toolkit._("Name or role is required.")}), 400
    # The quick-edit panel has no "active" checkbox (that's a full-edit-page
    # only field), so _contact_values() would otherwise read a missing form
    # field as unchecked and silently deactivate the contact point on every
    # quick edit. Preserve whatever it already was.
    values["active"] = item.active
    field_error = _contact_error(values, item)
    if field_error:
        return jsonify({"success": False, "error": field_error}), 409
    if _registry_uri_conflict(values["uri"], item):
        return jsonify({"success": False, "error": toolkit._("The URI is already used by a publisher or contact point.")}), 409
    for key, value in values.items():
        setattr(item, key, value)
    try:
        ckan_model.Session.add(item)
        ckan_model.Session.commit()
    except IntegrityError:
        ckan_model.Session.rollback()
        return jsonify({"success": False, "error": toolkit._("The URI is already in use.")}), 409
    return jsonify({"success": True, "contact_point": item.as_dict()})


@blueprint.route("/contactpoints/<item_id>")
def contactpoints_show(item_id):
    item = get_contact_point(item_id)
    if not item:
        abort(404)
    return toolkit.render(
        "actor_registry/contactpoint_show.html",
        extra_vars={
            "item": item,
            "actor": get_actor(item.actor_id) if item.actor_id else None,
            "linked": _linked_datasets("contact_point", [item_id]),
        },
    )


@blueprint.route("/contactpoints/<item_id>/datasets")
def contactpoints_datasets(item_id):
    item = get_contact_point(item_id)
    if not item:
        abort(404)
    page = _page_number()
    data = _linked_datasets("contact_point", [item_id], page=page, per_page=LIST_PAGE_SIZE)
    if page > 1 and not data["rows"]:
        abort(404)
    return toolkit.render(
        "actor_registry/linked_datasets.html",
        extra_vars={
            "item": item, "kind": "contact_point", "link": "contact_point", "data": data,
            "pager": _dataset_pager("actor_registry.contactpoints_datasets", page, data["total"], item_id=item_id),
        },
    )


@blueprint.route("/contactpoints/<item_id>/edit", methods=["GET", "POST"])
def contactpoints_edit(item_id):
    _require_login()
    item = get_contact_point(item_id)
    if not item:
        abort(404)
    if request.method == "POST":
        values = _contact_values(item)
        if not values["name"]:
            toolkit.h.flash_error(toolkit._("Name or role is required."))
        else:
            field_error = _contact_error(values, item)
            has_conflict = bool(field_error) or bool(_registry_uri_conflict(values["uri"], item))
            if field_error:
                toolkit.h.flash_error(field_error)
            elif has_conflict:
                toolkit.h.flash_error(toolkit._("The URI is already used by a publisher or contact point."))
            else:
                for key, value in values.items():
                    setattr(item, key, value)
            if not has_conflict and _commit(item, toolkit._("The URI is already used by a contact point.")):
                toolkit.h.flash_success(toolkit._("The contact point has been updated."))
                return redirect(toolkit.url_for("actor_registry.contactpoints_index"))
    return toolkit.render("actor_registry/contactpoint_form.html", extra_vars={"item": item, "actors": all_actors(), "is_new": False})


@blueprint.route("/contactpoints/<item_id>/delete", methods=["GET", "POST"])
def contactpoints_delete(item_id):
    # 2026-09-19, Björns beslut: samma sysadmin-only-gating och samma
    # tvåstegsbekräftelse som actors_delete.
    _require_sysadmin()
    item = get_contact_point(item_id)
    if not item:
        abort(404)

    if request.method == "POST":
        try:
            result = toolkit.get_action("actor_registry_contactpoint_delete")(
                {"user": g.user}, {"id": item_id}
            )
        except toolkit.ObjectNotFound:
            abort(404)
        toolkit.h.flash_success(
            toolkit._('The contact point "{name}" has been permanently deleted.').format(name=result["name"])
        )
        return redirect(toolkit.url_for("actor_registry.contactpoints_index"))

    linked_datasets = _linked_datasets("contact_point", [item_id])

    owning_actor = get_actor(item.actor_id) if item.actor_id else None

    return toolkit.render(
        "actor_registry/contactpoint_delete_confirm.html",
        extra_vars={"item": item, "linked_datasets": linked_datasets, "owning_actor": owning_actor},
    )


# The worklist of datasets that lack something. The URL parameter ``missing`` picks which:
# both a publisher and a contact point (the default), only the publisher, only the contact
# point, or either one.
MISSING_FILTERS = {
    "both": "none",
    "publisher": "no_publisher",
    "contact_point": "no_contact_point",
    "either": "either",
}


def _missing_filter():
    key = request.args.get("missing", "both")
    if key not in MISSING_FILTERS:
        abort(404)
    return key


def _missing_labels():
    return [
        ("both", toolkit._("Both")),
        ("publisher", toolkit._("Publisher")),
        ("contact_point", toolkit._("Contact point")),
        ("either", toolkit._("Either")),
    ]


def _missing_heading(key, total):
    return {
        "both": toolkit._("Datasets missing both a publisher and a contact point ({n})"),
        "publisher": toolkit._("Datasets without a publisher ({n})"),
        "contact_point": toolkit._("Datasets without a contact point ({n})"),
        "either": toolkit._("Datasets missing a publisher or a contact point ({n})"),
    }[key].format(n=total)


@blueprint.route("/actors")
def actors_index():
    _require_login()

    # 2026-09-19, Björns beslut: mergade/pensionerade aktörer (active=False)
    # ska vara dolda som standard -- de är sammanslagningsrester, inte
    # arbetsmaterial -- och bara visas om man aktivt kryssar i det. Tidigare
    # skickades all_actors(True) hit ovillkorligt, vilket var precis det som
    # gjorde listan skräpig.
    show_merged = request.args.get("show_merged") == "1"

    missing = _missing_filter()
    unlinked_datasets = _linked_datasets(MISSING_FILTERS[missing], [])

    return toolkit.render(
        "actor_registry/actors_index.html",
        extra_vars={
            "items": all_actors(show_merged),
            "show_merged": show_merged,
            "unlinked_datasets": unlinked_datasets,
            "missing": missing,
            "missing_labels": _missing_labels(),
            "missing_heading": _missing_heading(missing, unlinked_datasets["total"]),
        },
    )


@blueprint.route("/actors/unlinked-datasets")
def actors_unlinked_datasets():
    """All datasets that lack a publisher and/or a contact point (see ``missing``), paginated."""
    _require_login()
    missing = _missing_filter()
    page = _page_number()
    data = _linked_datasets(MISSING_FILTERS[missing], [], page=page, per_page=LIST_PAGE_SIZE)
    if page > 1 and not data["rows"]:
        abort(404)
    return toolkit.render(
        "actor_registry/linked_datasets.html",
        extra_vars={
            "item": None, "kind": "unlinked", "link": MISSING_FILTERS[missing], "data": data,
            "missing": missing, "heading": _missing_heading(missing, data["total"]),
            "pager": _dataset_pager("actor_registry.actors_unlinked_datasets", page, data["total"], missing=missing),
        },
    )


@blueprint.route("/actors/new", methods=["GET", "POST"])
def actors_new():
    _require_login()
    values = _actor_values()
    if request.method == "POST" and values["name"]:
        item_id = str(uuid.uuid4())
        values["uri"] = values["uri"] or toolkit.url_for("actor_registry.actors_show", item_id=item_id, _external=True)
        identifier_error = _actor_error(values)
        if identifier_error:
            toolkit.h.flash_error(identifier_error)
        elif _registry_uri_conflict(values["uri"]):
            toolkit.h.flash_error(toolkit._("The URI is already used by a publisher or contact point."))
        elif _commit(Actor(id=item_id, **values), toolkit._("The URI is already used by a publisher.")):
            toolkit.h.flash_success(toolkit._("The publisher has been created."))
            return redirect(toolkit.url_for("actor_registry.actors_index"))
    elif request.method == "POST":
        toolkit.h.flash_error(toolkit._("Name is required."))
    return toolkit.render("actor_registry/actor_form.html", extra_vars={"item": values, "is_new": True})


@blueprint.route("/actors/quick-create", methods=["POST"])
def actors_quick_create():
    _require_login()
    values = _actor_values()
    if not values["name"]:
        return jsonify({"success": False, "error": toolkit._("Name is required.")}), 400
    item_id = str(uuid.uuid4())
    values["uri"] = values["uri"] or toolkit.url_for("actor_registry.actors_show", item_id=item_id, _external=True)
    values["active"] = True
    identifier_error = _actor_error(values)
    if identifier_error:
        return jsonify({"success": False, "error": identifier_error}), 409
    if _registry_uri_conflict(values["uri"]):
        return jsonify({"success": False, "error": toolkit._("The URI is already used by a publisher or contact point.")}), 409
    item = Actor(id=item_id, **values)
    try:
        ckan_model.Session.add(item)
        ckan_model.Session.commit()
    except IntegrityError:
        ckan_model.Session.rollback()
        return jsonify({"success": False, "error": _integrity_message(values, None, toolkit._("The URI is already in use."))}), 409
    return jsonify({"success": True, "actor": item.as_dict()})


@blueprint.route("/actors/<item_id>/quick-edit", methods=["POST"])
def actors_quick_edit(item_id):
    _require_login()
    item = get_actor(item_id)
    if not item:
        return jsonify({"success": False, "error": toolkit._("The publisher was not found.")}), 404
    values = _actor_values(item)
    if not values["name"]:
        return jsonify({"success": False, "error": toolkit._("Name is required.")}), 400
    # Same reasoning as contactpoints_quick_edit: the quick-edit panel has
    # no "active" checkbox, so preserve the existing value instead of
    # letting _actor_values() read the missing field as unchecked.
    values["active"] = item.active
    identifier_error = _actor_error(values, item)
    if identifier_error:
        return jsonify({"success": False, "error": identifier_error}), 409
    if _registry_uri_conflict(values["uri"], item):
        return jsonify({"success": False, "error": toolkit._("The URI is already used by a publisher or contact point.")}), 409
    for key, value in values.items():
        setattr(item, key, value)
    try:
        ckan_model.Session.add(item)
        ckan_model.Session.commit()
    except IntegrityError:
        ckan_model.Session.rollback()
        return jsonify({"success": False, "error": toolkit._("The URI is already in use.")}), 409
    return jsonify({"success": True, "actor": item.as_dict()})


@blueprint.route("/actors/<item_id>")
def actors_show(item_id):
    item = get_actor(item_id)
    if not item:
        abort(404)

    merged_into = get_actor(item.merged_into_id) if item.merged_into_id else None

    linked = {"publisher": {"rows": [], "total": 0}}
    if item.active:
        linked = {"publisher": _linked_datasets("publisher", [item_id])}

    return toolkit.render(
        "actor_registry/actor_show.html",
        extra_vars={"item": item, "merged_into": merged_into, "linked": linked},
    )


@blueprint.route("/actors/<item_id>/datasets")
def actors_datasets(item_id):
    item = get_actor(item_id)
    if not item:
        abort(404)
    # Only the datasets this actor PUBLISHES are listed; an actor is not a
    # contact point, so there is no "via its contact points" list.
    if request.args.get("link", "publisher") != "publisher":
        abort(404)
    page = _page_number()
    data = _linked_datasets("publisher", [item_id], page=page, per_page=LIST_PAGE_SIZE)
    if page > 1 and not data["rows"]:
        abort(404)
    return toolkit.render(
        "actor_registry/linked_datasets.html",
        extra_vars={
            "item": item, "kind": "actor", "link": "publisher", "data": data,
            "pager": _dataset_pager("actor_registry.actors_datasets", page, data["total"], item_id=item_id, link="publisher"),
        },
    )


@blueprint.route("/actors/<item_id>/edit", methods=["GET", "POST"])
def actors_edit(item_id):
    _require_login()
    item = get_actor(item_id)
    if not item:
        abort(404)
    if request.method == "POST":
        values = _actor_values(item)
        if not values["name"]:
            toolkit.h.flash_error(toolkit._("Name is required."))
        else:
            identifier_error = _actor_error(values, item)
            has_conflict = bool(identifier_error) or bool(_registry_uri_conflict(values["uri"], item))
            if identifier_error:
                toolkit.h.flash_error(identifier_error)
            elif has_conflict:
                toolkit.h.flash_error(toolkit._("The URI is already used by a publisher or contact point."))
            else:
                for key, value in values.items():
                    setattr(item, key, value)
            if not has_conflict and _commit(item, toolkit._("The URI is already used by a publisher.")):
                toolkit.h.flash_success(toolkit._("The publisher has been updated."))
                return redirect(toolkit.url_for("actor_registry.actors_index"))
    return toolkit.render("actor_registry/actor_form.html", extra_vars={"item": item, "is_new": False})


def _parse_merge_ids(raw):
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


@blueprint.route("/actors/<item_id>/delete", methods=["GET", "POST"])
def actors_delete(item_id):
    # 2026-09-19, Björns beslut: precis som sammanslagning är permanent
    # borttagning sysadmin-only -- den är irreversibel (till skillnad från
    # merge finns ingen merged_into_id att falla tillbaka på efteråt) och
    # kan påverka datamängder över hela katalogen.
    _require_sysadmin()
    item = get_actor(item_id)
    if not item:
        abort(404)

    if request.method == "POST":
        try:
            result = toolkit.get_action("actor_registry_actor_delete")(
                {"user": g.user}, {"id": item_id}
            )
        except toolkit.ObjectNotFound:
            abort(404)
        toolkit.h.flash_success(
            toolkit._('The publisher "{name}" has been permanently deleted.').format(name=result["name"])
        )
        return redirect(toolkit.url_for("actor_registry.actors_index"))

    linked_datasets = {"publisher": _linked_datasets("publisher", [item_id])}

    owned_contact_points = (
        ckan_model.Session.query(ContactPoint)
        .filter(ContactPoint.actor_id == item_id)
        .order_by(ContactPoint.name.asc())
        .all()
    )
    chained_actors = registry_model.actors_merged_into(item_id)

    return toolkit.render(
        "actor_registry/actor_delete_confirm.html",
        extra_vars={
            "item": item,
            "linked": linked_datasets,
            "owned_contact_points": owned_contact_points,
            "chained_actors": chained_actors,
        },
    )


@blueprint.route("/actors/merge", methods=["GET", "POST"])
def actors_merge():
    _require_sysadmin()
    if request.method == "POST":
        actor_a_id = request.form.get("actor_a_id", "")
        actor_b_id = request.form.get("actor_b_id", "")
    else:
        parsed = _parse_merge_ids(request.args.get("ids", ""))
        actor_a_id = parsed[0] if len(parsed) > 0 else ""
        actor_b_id = parsed[1] if len(parsed) > 1 else ""

    if not actor_a_id or not actor_b_id or actor_a_id == actor_b_id:
        toolkit.h.flash_error(toolkit._("Select exactly two different publishers to merge."))
        return redirect(toolkit.url_for("actor_registry.actors_index"))

    actor_a = get_actor(actor_a_id)
    actor_b = get_actor(actor_b_id)
    if not actor_a or not actor_a.active or not actor_b or not actor_b.active:
        toolkit.h.flash_error(toolkit._("One or both publishers were not found, or are already inactive."))
        return redirect(toolkit.url_for("actor_registry.actors_index"))

    if request.method == "POST":
        keep_id = request.form.get("keep_id")
        if keep_id not in (actor_a_id, actor_b_id):
            toolkit.h.flash_error(toolkit._("You must choose which publisher should remain."))
        else:
            merge_id = actor_b_id if keep_id == actor_a_id else actor_a_id
            fields = {}
            for field_name in MERGEABLE_FIELDS:
                override = request.form.get("override_" + field_name, "").strip()
                if override:
                    fields[field_name] = override
                else:
                    side = request.form.get("field_" + field_name)
                    source = actor_b if side == "b" else actor_a
                    fields[field_name] = getattr(source, field_name) or ""
            try:
                toolkit.get_action("actor_registry_actor_merge")(
                    {"user": g.user},
                    {"keep_id": keep_id, "merge_id": merge_id, "fields": fields},
                )
            except (toolkit.ValidationError, toolkit.ObjectNotFound) as error:
                toolkit.h.flash_error(toolkit._("Could not merge the publishers: {0}").format(error))
            else:
                toolkit.h.flash_success(toolkit._("The publishers have been merged."))
                return redirect(toolkit.url_for("actor_registry.actors_show", item_id=keep_id))

    linked_a = registry_model.datasets_for_actor(actor_a_id)
    linked_b = registry_model.datasets_for_actor(actor_b_id)
    return toolkit.render(
        "actor_registry/actors_merge.html",
        extra_vars={
            "actor_a": actor_a,
            "actor_b": actor_b,
            "fields": MERGEABLE_FIELDS,
            "field_labels": _merge_field_labels(),
            "linked_a": linked_a,
            "linked_b": linked_b,
        },
    )


@blueprint.route("/dataset/<package_id>/actor-link", methods=["POST"])
def dataset_actor_link(package_id):
    """Let anyone who can edit this dataset fill in a missing publisher
    and/or contact-point link directly from the dataset's own read page,
    without going through the full dataset edit form. Reuses the same
    field snippets (actors_multiple_select.html /
    contactpoints_multiple_select.html) as that form, per Björn's
    explicit request (2026-09-15) that people "recognize" the control.

    A partial update (package_patch), not package_update: only the
    field(s) actually posted are touched, everything else on the
    dataset is left alone.
    """
    pkg = ckan_model.Package.get(package_id)
    if not pkg:
        abort(404)

    try:
        toolkit.check_access("package_update", {"user": g.user}, {"id": pkg.id})
    except toolkit.NotAuthorized:
        abort(403)

    patch = {"id": pkg.id}
    if "publisher_actor_id" in request.form:
        patch["publisher_actor_id"] = request.form.get("publisher_actor_id", "").strip()
    if "contact_point_ids" in request.form:
        patch["contact_point_ids"] = [
            value for value in request.form.getlist("contact_point_ids") if value
        ]

    try:
        toolkit.get_action("package_patch")({"user": g.user}, patch)
    except toolkit.ValidationError as error:
        toolkit.h.flash_error(toolkit._("Could not save the publisher link: {0}").format(error.error_summary))
    except toolkit.NotAuthorized:
        abort(403)
    else:
        toolkit.h.flash_success(toolkit._("The publisher link has been saved."))

    return redirect(toolkit.url_for("dataset.read", id=pkg.name))
