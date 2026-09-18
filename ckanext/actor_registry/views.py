import uuid

from ckan import model as ckan_model
from ckan.plugins import toolkit
from flask import Blueprint, abort, g, jsonify, redirect, request
from sqlalchemy.exc import IntegrityError

from ckanext.actor_registry import model as registry_model
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


@blueprint.route("/contactpoints")
def contactpoints_index():
    _require_login()
    return toolkit.render("actor_registry/contactpoints_index.html", extra_vars={"items": all_contact_points(True)})


@blueprint.route("/contactpoints/new", methods=["GET", "POST"])
def contactpoints_new():
    _require_login()
    values = _contact_values()
    if request.method == "POST" and values["name"]:
        item_id = str(uuid.uuid4())
        values["uri"] = values["uri"] or toolkit.url_for("actor_registry.contactpoints_show", item_id=item_id, _external=True)
        if _registry_uri_conflict(values["uri"]):
            toolkit.h.flash_error(toolkit._("The URI is already used by an actor or contact point."))
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
    if _registry_uri_conflict(values["uri"]):
        return jsonify({"success": False, "error": toolkit._("The URI is already used by an actor or contact point.")}), 409
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
    if _registry_uri_conflict(values["uri"], item):
        return jsonify({"success": False, "error": toolkit._("The URI is already used by an actor or contact point.")}), 409
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
    return toolkit.render("actor_registry/contactpoint_show.html", extra_vars={"item": item, "actor": get_actor(item.actor_id) if item.actor_id else None})


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
            has_conflict = bool(_registry_uri_conflict(values["uri"], item))
            if has_conflict:
                toolkit.h.flash_error(toolkit._("The URI is already used by an actor or contact point."))
            else:
                for key, value in values.items():
                    setattr(item, key, value)
            if not has_conflict and _commit(item, toolkit._("The URI is already used by a contact point.")):
                toolkit.h.flash_success(toolkit._("The contact point has been updated."))
                return redirect(toolkit.url_for("actor_registry.contactpoints_index"))
    return toolkit.render("actor_registry/contactpoint_form.html", extra_vars={"item": item, "actors": all_actors(), "is_new": False})


@blueprint.route("/actors")
def actors_index():
    _require_login()

    unlinked_ids = registry_model.datasets_without_actor_link()
    unlinked_datasets = []
    if unlinked_ids:
        context = {"user": g.user}
        fq = "id:({0})".format(" OR ".join(unlinked_ids))
        result = toolkit.get_action("package_search")(
            context, {"fq": fq, "rows": len(unlinked_ids)}
        )
        unlinked_datasets = result["results"]

    return toolkit.render(
        "actor_registry/actors_index.html",
        extra_vars={"items": all_actors(True), "unlinked_datasets": unlinked_datasets},
    )


@blueprint.route("/actors/new", methods=["GET", "POST"])
def actors_new():
    _require_login()
    values = _actor_values()
    if request.method == "POST" and values["name"]:
        item_id = str(uuid.uuid4())
        values["uri"] = values["uri"] or toolkit.url_for("actor_registry.actors_show", item_id=item_id, _external=True)
        if _registry_uri_conflict(values["uri"]):
            toolkit.h.flash_error(toolkit._("The URI is already used by an actor or contact point."))
        elif _commit(Actor(id=item_id, **values), toolkit._("The URI is already used by an actor.")):
            toolkit.h.flash_success(toolkit._("The actor has been created."))
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
    if _registry_uri_conflict(values["uri"]):
        return jsonify({"success": False, "error": toolkit._("The URI is already used by an actor or contact point.")}), 409
    item = Actor(id=item_id, **values)
    try:
        ckan_model.Session.add(item)
        ckan_model.Session.commit()
    except IntegrityError:
        ckan_model.Session.rollback()
        return jsonify({"success": False, "error": toolkit._("The URI is already in use.")}), 409
    return jsonify({"success": True, "actor": item.as_dict()})


@blueprint.route("/actors/<item_id>/quick-edit", methods=["POST"])
def actors_quick_edit(item_id):
    _require_login()
    item = get_actor(item_id)
    if not item:
        return jsonify({"success": False, "error": toolkit._("The actor was not found.")}), 404
    values = _actor_values(item)
    if not values["name"]:
        return jsonify({"success": False, "error": toolkit._("Name is required.")}), 400
    # Same reasoning as contactpoints_quick_edit: the quick-edit panel has
    # no "active" checkbox, so preserve the existing value instead of
    # letting _actor_values() read the missing field as unchecked.
    values["active"] = item.active
    if _registry_uri_conflict(values["uri"], item):
        return jsonify({"success": False, "error": toolkit._("The URI is already used by an actor or contact point.")}), 409
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

    linked = {"publisher": [], "contact_point": []}
    if item.active:
        ids = registry_model.datasets_for_actor(item_id)
        context = {"user": g.user}
        for link_type, candidate_ids in ids.items():
            if not candidate_ids:
                continue
            fq = "id:({0})".format(" OR ".join(candidate_ids))
            result = toolkit.get_action("package_search")(
                context, {"fq": fq, "rows": len(candidate_ids)}
            )
            linked[link_type] = result["results"]

    return toolkit.render(
        "actor_registry/actor_show.html",
        extra_vars={"item": item, "merged_into": merged_into, "linked": linked},
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
            has_conflict = bool(_registry_uri_conflict(values["uri"], item))
            if has_conflict:
                toolkit.h.flash_error(toolkit._("The URI is already used by an actor or contact point."))
            else:
                for key, value in values.items():
                    setattr(item, key, value)
            if not has_conflict and _commit(item, toolkit._("The URI is already used by an actor.")):
                toolkit.h.flash_success(toolkit._("The actor has been updated."))
                return redirect(toolkit.url_for("actor_registry.actors_index"))
    return toolkit.render("actor_registry/actor_form.html", extra_vars={"item": item, "is_new": False})


def _parse_merge_ids(raw):
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


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
        toolkit.h.flash_error(toolkit._("Select exactly two different actors to merge."))
        return redirect(toolkit.url_for("actor_registry.actors_index"))

    actor_a = get_actor(actor_a_id)
    actor_b = get_actor(actor_b_id)
    if not actor_a or not actor_a.active or not actor_b or not actor_b.active:
        toolkit.h.flash_error(toolkit._("One or both actors were not found, or are already inactive."))
        return redirect(toolkit.url_for("actor_registry.actors_index"))

    if request.method == "POST":
        keep_id = request.form.get("keep_id")
        if keep_id not in (actor_a_id, actor_b_id):
            toolkit.h.flash_error(toolkit._("You must choose which actor should remain."))
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
                toolkit.h.flash_error(toolkit._("Could not merge the actors: {0}").format(error))
            else:
                toolkit.h.flash_success(toolkit._("The actors have been merged."))
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
        toolkit.h.flash_error(toolkit._("Could not save the actor link: {0}").format(error.error_summary))
    except toolkit.NotAuthorized:
        abort(403)
    else:
        toolkit.h.flash_success(toolkit._("The actor link has been saved."))

    return redirect(toolkit.url_for("dataset.read", id=pkg.name))
