import re
import uuid

from ckan import authz
from ckan.lib.helpers import Page
from ckan import model as ckan_model
from ckan.plugins import toolkit
from flask import Blueprint, abort, g, jsonify, redirect, request
from sqlalchemy.exc import IntegrityError

from ckanext.actor_registry import cleanup, contact_migration, helpers, language
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


def _merge_languages(*actors):
    """The languages either publisher has a translation in, the portal's own first (0.7.0)."""
    found = {row.lang for actor in actors for row in actor.translations}
    offered = [code for code in language.offered_languages() if code in found]
    return offered + sorted(found - set(offered))


def _merge_fields(actor_a, actor_b):
    """The rows of the merge table: the publisher's fields, then name and description per language
    (``name@sv``, ``description@sv``)."""
    fields = list(MERGEABLE_FIELDS)
    for code in _merge_languages(actor_a, actor_b):
        fields += ["name@" + code, "description@" + code]
    return fields


def _merge_values(actor):
    values = {name: getattr(actor, name) or "" for name in MERGEABLE_FIELDS}
    for code, entry in actor.translations_dict().items():
        values["name@" + code] = entry.get("name") or ""
        values["description@" + code] = entry.get("description") or ""
    return values


def _merge_field_labels(actor_a=None, actor_b=None):
    # Translated lazily, at request time -- see the note in
    # claude/i18n-plan.md-derived work: a module-level dict built at
    # import time would bake in whatever locale happened to be active
    # when the app first loaded the module, not the current visitor's.
    labels = {key: toolkit._(value) for key, value in MERGE_FIELD_LABELS.items()}
    if actor_a is not None:
        for code in _merge_languages(actor_a, actor_b):
            name = language.language_name(code)
            labels["name@" + code] = toolkit._("Name in {language}").format(language=name)
            labels["description@" + code] = toolkit._("Description in {language}").format(language=name)
    return labels


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

def _form_language_codes(item=None):
    """The languages of the form's Translations: the ones the portal offers besides its default one, then any other
    language the record already has a name in (shown so that it can be seen and removed)."""
    codes = language.offered_languages()
    if isinstance(item, (Actor, ContactPoint)):
        codes += sorted(row.lang for row in item.translations if row.lang not in codes)
    return codes


def _translation_languages(item=None):
    """``[(code, name)]`` for the form's Translations."""
    return [(code, language.language_name(code)) for code in _form_language_codes(item)]


def _translation_values(item=None, with_description=False):
    """The translations a form sent, laid over the record's own, or None when the form had no Translations (the
    quick dialogs): then they are left as they are."""
    if request.form.get("translations_form") != "1":
        return None
    values = item.translations_dict() if item is not None else {}
    for code in _form_language_codes(item):
        # Only the languages the form sent: the quick panels in the dataset form send names for the offered
        # languages and no descriptions, and what they do not show stays as it was.
        if "translation_name-" + code not in request.form:
            continue
        entry = dict(values.get(code) or {})
        entry["name"] = request.form.get("translation_name-" + code, "").strip()
        if with_description and "translation_description-" + code in request.form:
            entry["description"] = request.form.get("translation_description-" + code, "").strip()
        values[code] = entry
    return values


def _translation_error(values):
    """The first problem with the translations a form sent, or None."""
    for code, entry in (values or {}).items():
        name = language.language_name(code)
        if len(entry.get("name") or "") > 255:
            return toolkit._("The name in {language} is too long (at most {limit} characters).").format(
                language=name, limit=255)
        if (entry.get("description") or "") and not entry.get("name"):
            return toolkit._("The description in {language} needs a name in {language} too.").format(language=name)
    return None


def _form_translations(item, posted):
    """What the form's Translations show: what was sent, or the record's own."""
    if posted is not None:
        return posted
    return item.translations_dict() if isinstance(item, (Actor, ContactPoint)) else {}


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


def _linked_datasets(link, subject_ids, page=1, per_page=PREVIEW_SIZE, filters=None):
    is_sysadmin, org_ids = _viewer_visibility()
    # A dataset lacks a publisher or a contact point only when its type has the field (0.6.0).
    field_types = cleanup.field_types() if link in registry_model.MISSING_MODES else None
    rows, total = registry_model.linked_datasets(
        link, subject_ids, is_sysadmin=is_sysadmin, org_ids=org_ids, page=page, per_page=per_page,
        field_types=field_types, filters=filters,
    )
    return {"rows": rows, "total": total}


TODO_FILTER_LIMIT = 10


def _todo_filters(source):
    """The To do page's search and filters (0.6.0): text, tags (a dataset has them all) and
    organisations (it belongs to one of them). ``source`` is ``request.args`` or ``request.form``."""
    filters = {}
    q = (source.get("q") or "").strip()[:200]
    if q:
        filters["q"] = q
    for key in ("tag", "org"):
        values = []
        for value in source.getlist(key):
            value = (value or "").strip()[:200]
            if value and value not in values:
                values.append(value)
        if values:
            filters[key] = values[:TODO_FILTER_LIMIT]
    return filters


def _todo_url(missing, filters, **args):
    """The To do page with these filters; it opens at the filters (or ``_anchor``), not at the top."""
    args.setdefault("_anchor", "todo-filters")
    return toolkit.url_for("actor_registry.todo_index", missing=missing, **dict(filters, **args))


def _todo_facets(missing, filters):
    """The tags and organisations to add to the filters, and the chosen ones, each with a link that removes it."""
    is_sysadmin, org_ids = _viewer_visibility()
    facets = registry_model.linked_dataset_facets(
        MISSING_FILTERS[missing], is_sysadmin=is_sysadmin, org_ids=org_ids,
        field_types=cleanup.field_types(), filters=filters)
    chosen_tags, chosen_orgs = filters.get("tag", []), filters.get("org", [])
    # A chosen organisation keeps its name when none of its datasets is left (after the last one was saved).
    titles = {item[0]: item[1] for item in facets["organizations"]}
    for org_id in chosen_orgs:
        if org_id not in titles:
            group = ckan_model.Group.get(org_id)
            if group is not None and group.is_organization and group.state == "active":
                titles[org_id] = group.title or group.name
    facets["tags"] = [item for item in facets["tags"] if item[0] not in chosen_tags]
    facets["organizations"] = [item for item in facets["organizations"] if item[0] not in chosen_orgs]

    def without(key, value):
        rest = dict(filters, **{key: [item for item in filters[key] if item != value]})
        return _todo_url(missing, {k: v for k, v in rest.items() if v})
    facets["chosen"] = (
        [{"label": toolkit._("Tag: {name}").format(name=tag), "url": without("tag", tag)} for tag in chosen_tags]
        + [{"label": toolkit._("Organization: {name}").format(name=titles.get(org_id, org_id)), "url": without("org", org_id)}
           for org_id in chosen_orgs])
    return facets


def _todo_tabs():
    """The tabs of To do (0.6.0): what is missing, and, for those who may clean up, the inactive or
    removed publishers and contact points that datasets still use (the clean-up page)."""
    tabs = [{"url": toolkit.url_for("actor_registry.todo_index"), "label": toolkit._("Missing"),
             "count": helpers.todo_count(), "endpoint": "actor_registry.todo_index"}]
    if contact_migration.can_migrate(g.user):
        tabs.append({"url": toolkit.url_for("actor_registry.cleanup_index"), "label": toolkit._("Inactive or removed"),
                     "count": helpers.cleanup_count(), "endpoint": "actor_registry.cleanup_index"})
    return tabs


def _contact_point_tabs():
    """The tabs of Contact points (0.6.0): the list, and while the migration is open, creating contact
    points from the datasets' old contact fields (the migration page). That tab shows while datasets
    wait or skipped ones are left, and always for a sysadmin, who may need it for datasets harvested
    or imported later; its number counts only those that wait."""
    tabs = [{"url": toolkit.url_for("actor_registry.contactpoints_index", list=1), "label": toolkit._("Contact points"),
             "count": 0, "endpoint": "actor_registry.contactpoints_index"}]
    if not contact_migration.can_migrate(g.user):
        return tabs
    on_it = request.endpoint == "actor_registry.migrate_index"
    if not on_it and contact_migration.is_closed():
        return tabs
    counts = helpers.migration_counts()
    if on_it or counts["remaining"] or counts["skipped"] or authz.is_sysadmin(g.user):
        tabs.append({"url": toolkit.url_for("actor_registry.migrate_index"),
                     "label": toolkit._("Create contact points from the datasets"),
                     "count": counts["remaining"], "endpoint": "actor_registry.migrate_index"})
    return tabs


def _names(rows):
    """The names of the publishers and contact points set on the rows, for To do (0.6.0)."""
    actors = {item.id: item.display_name for item in all_actors(True)}
    contact_points = {item.id: item.display_name for item in all_contact_points(True)}
    for row in rows:
        row["publisher_name"] = actors.get(row.get("publisher_id"), "")
        row["contact_point_names"] = [contact_points.get(item, "") for item in row.get("contact_point_ids", [])]
    return rows


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
    everything = all_contact_points(True)
    # While datasets wait for the migration, Contact points opens on it from the menu (0.6.0); with only skipped ones
    # left it opens on the list. Any address with an argument shows the list: the tab "Contact points" and the
    # registry's own links (list=1), and the box for inactive ones (show_inactive).
    if contact_migration.can_migrate(g.user) and not contact_migration.is_closed() and not request.args:
        if helpers.migration_remaining_count():
            return redirect(toolkit.url_for("actor_registry.migrate_index"))
    return toolkit.render(
        "actor_registry/contactpoints_index.html",
        extra_vars={"items": everything if show_inactive else [item for item in everything if item.active],
                    "show_inactive": show_inactive,
                    "tabs": _contact_point_tabs(),
                    "migration_closed": contact_migration.is_closed(),
                    # The box (and its help text) only when there is something to show (0.6.0).
                    "inactive_count": sum(1 for item in everything if not item.active)},
    )


@blueprint.route("/contactpoints/new", methods=["GET", "POST"])
def contactpoints_new():
    _require_login()
    values = _contact_values()
    translations = _translation_values()
    if request.method == "POST" and values["name"]:
        item_id = str(uuid.uuid4())
        values["uri"] = values["uri"] or toolkit.url_for("actor_registry.contactpoints_show", item_id=item_id, _external=True, locale="default")
        field_error = _contact_error(values) or _translation_error(translations)
        if field_error:
            toolkit.h.flash_error(field_error)
        elif _registry_uri_conflict(values["uri"]):
            toolkit.h.flash_error(toolkit._("The URI is already used by a publisher or contact point."))
        else:
            item = ContactPoint(id=item_id, **values)
            item.set_translations(translations or {})
            if _commit(item, toolkit._("The URI is already used by a contact point.")):
                toolkit.h.flash_success(toolkit._("The contact point has been created."))
                return redirect(toolkit.url_for("actor_registry.contactpoints_index", list=1))
    elif request.method == "POST":
        toolkit.h.flash_error(toolkit._("Name or role is required."))
    return toolkit.render("actor_registry/contactpoint_form.html", extra_vars={
        "item": values, "actors": all_actors(), "is_new": True,
        "languages": _translation_languages(), "translations": translations or {}})


@blueprint.route("/contactpoints/quick-create", methods=["POST"])
def contactpoints_quick_create():
    _require_login()
    values = _contact_values()
    if not values["name"]:
        return jsonify({"success": False, "error": toolkit._("Name or role is required.")}), 400
    item_id = str(uuid.uuid4())
    values["uri"] = values["uri"] or toolkit.url_for("actor_registry.contactpoints_show", item_id=item_id, _external=True, locale="default")
    values["active"] = True
    field_error = _contact_error(values)
    if field_error:
        return jsonify({"success": False, "error": field_error}), 409
    if _registry_uri_conflict(values["uri"]):
        return jsonify({"success": False, "error": toolkit._("The URI is already used by a publisher or contact point.")}), 409
    translations = _translation_values()
    translation_error = _translation_error(translations)
    if translation_error:
        return jsonify({"success": False, "error": translation_error}), 400
    item = ContactPoint(id=item_id, **values)
    item.set_translations(translations or {})
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
    translations = _translation_values(item)
    translation_error = _translation_error(translations)
    if translation_error:
        return jsonify({"success": False, "error": translation_error}), 400
    for key, value in values.items():
        setattr(item, key, value)
    if translations is not None:
        item.set_translations(translations)
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
    translations = None
    if request.method == "POST":
        values = _contact_values(item)
        translations = _translation_values(item)
        if not values["name"]:
            toolkit.h.flash_error(toolkit._("Name or role is required."))
        else:
            field_error = _contact_error(values, item) or _translation_error(translations)
            has_conflict = bool(field_error) or bool(_registry_uri_conflict(values["uri"], item))
            if field_error:
                toolkit.h.flash_error(field_error)
            elif has_conflict:
                toolkit.h.flash_error(toolkit._("The URI is already used by a publisher or contact point."))
            else:
                for key, value in values.items():
                    setattr(item, key, value)
                if translations is not None:
                    item.set_translations(translations)
            if not has_conflict and _commit(item, toolkit._("The URI is already used by a contact point.")):
                toolkit.h.flash_success(toolkit._("The contact point has been updated."))
                return redirect(toolkit.url_for("actor_registry.contactpoints_index", list=1))
    return toolkit.render("actor_registry/contactpoint_form.html", extra_vars={
        "item": item, "actors": all_actors(), "is_new": False,
        "languages": _translation_languages(item), "translations": _form_translations(item, translations)})


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
        return redirect(toolkit.url_for("actor_registry.contactpoints_index", list=1))

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


def _missing_filter(default="both"):
    key = request.args.get("missing", default)
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


def _missing_counts(selected, selected_total, filters=None):
    """How many datasets each choice of "Missing" lists, for the viewer. One count query each; the chosen one is already known."""
    counts = {}
    for key, link in MISSING_FILTERS.items():
        counts[key] = selected_total if key == selected else _linked_datasets(link, [], per_page=1, filters=filters)["total"]
    return counts


def _missing_heading(key, total):
    return {
        "both": toolkit._("Datasets missing both a publisher and a contact point ({n})"),
        "publisher": toolkit._("Datasets without a publisher ({n})"),
        "contact_point": toolkit._("Datasets without a contact point ({n})"),
        "either": toolkit._("Datasets missing a publisher or a contact point ({n})"),
    }[key].format(n=total)


TODO_DEFAULT = "either"


def _assign_choices(rows):
    """What the To do list needs to let the viewer set links: the ids of the rows they may edit
    and the active publishers and contact points. None when they may edit none of the rows."""
    all_datasets, org_ids = contact_migration.editable_scope(g.user)
    org_ids = set(org_ids)
    ids = {row["id"] for row in rows if all_datasets or row.get("owner_org") in org_ids}
    if not ids:
        return None
    editable = [row for row in rows if row["id"] in ids]
    return {
        "ids": ids, "actors": all_actors(), "contact_points": all_contact_points(),
        # A choice in the bars only when some editable row lacks it (and its type has the field).
        "publisher": any(row["publisher_field"] and not row["has_publisher"] for row in editable),
        "contact_point": any(row["contact_point_field"] and not row["has_contact_point"] for row in editable),
    }


@blueprint.route("/actors")
def actors_index():
    _require_login()
    # The list of datasets that lack a publisher or a contact point moved to its own page (0.6.0).
    if "missing" in request.args:
        return redirect(toolkit.url_for("actor_registry.todo_index", missing=request.args.get("missing")), code=301)

    # 2026-09-19, Björns beslut: mergade/pensionerade aktörer (active=False)
    # ska vara dolda som standard -- de är sammanslagningsrester, inte
    # arbetsmaterial -- och bara visas om man aktivt kryssar i det. Tidigare
    # skickades all_actors(True) hit ovillkorligt, vilket var precis det som
    # gjorde listan skräpig.
    show_merged = request.args.get("show_merged") == "1"

    everything = all_actors(True)
    return toolkit.render(
        "actor_registry/actors_index.html",
        extra_vars={
            "items": everything if show_merged else [item for item in everything if item.active],
            "show_merged": show_merged,
            # The box (and its help text) only when there are merged or retired publishers,
            # and merging only when there are two to merge (0.6.0).
            "retired_count": sum(1 for item in everything if not item.active),
            "active_count": sum(1 for item in everything if item.active),
        },
    )


@blueprint.route("/actors/unlinked-datasets")
def actors_unlinked_datasets():
    """Moved to the To do page (0.6.0); old links still lead there."""
    # Without ``missing`` this list meant "both", unlike To do's default.
    args = {"missing": request.args.get("missing", "both")}
    if "page" in request.args:
        args["page"] = request.args["page"]
    return redirect(toolkit.url_for("actor_registry.todo_index", **args), code=301)


@blueprint.route("/actor-registry/todo", strict_slashes=False)
def todo_index():
    """The datasets that lack a publisher and/or a contact point (see ``missing``), paginated,
    where an editor sets them on one row or on many at once (0.6.0)."""
    _require_login()
    missing = _missing_filter(TODO_DEFAULT)
    page = _page_number()
    filters = _todo_filters(request.args)
    data = _linked_datasets(MISSING_FILTERS[missing], [], page=page, per_page=LIST_PAGE_SIZE, filters=filters)
    last = max(1, -(-data["total"] // LIST_PAGE_SIZE))
    # After the last rows of the last page are done, that page no longer exists: go to the new last one.
    if page > last:
        return redirect(_todo_url(missing, filters, page=last, _anchor="todo-list"))
    _names(data["rows"])
    return toolkit.render(
        "actor_registry/todo.html",
        extra_vars={
            "data": data, "missing": missing, "page": page, "filters": filters,
            "facets": _todo_facets(missing, filters),
            "tabs": _todo_tabs(),
            "missing_labels": _missing_labels(),
            "missing_counts": _missing_counts(missing, data["total"], filters),
            "heading": _missing_heading(missing, data["total"]),
            "pager": _dataset_pager("actor_registry.todo_index", page, data["total"], missing=missing,
                                    _anchor="todo-list", **filters),
            "assign": _assign_choices(data["rows"]),
        },
    )


def _flash_assignments(results):
    """One message per publisher and contact point that was set, however many groups of rows it was saved in."""
    changed = {"publisher": {}, "contact_point": {}}
    skipped = {"publisher": 0, "contact_point": 0}
    failures = []
    for result in results:
        for kind, record in (("publisher", result["actor"]), ("contact_point", result["contact_point"])):
            if result["changed"][kind]:
                name, count = changed[kind].get(record.id, (record.display_name, 0))
                changed[kind][record.id] = (name, count + len(result["changed"][kind]))
            skipped[kind] += len(result["skipped"][kind])
        failures += result["failures"]
    for name, count in changed["publisher"].values():
        toolkit.h.flash_success(toolkit.ungettext(
            "{name} is now the publisher of {count} dataset.",
            "{name} is now the publisher of {count} datasets.", count).format(count=count, name=name))
    for name, count in changed["contact_point"].values():
        toolkit.h.flash_success(toolkit.ungettext(
            "{name} is now the contact point of {count} dataset.",
            "{name} is now the contact point of {count} datasets.", count).format(count=count, name=name))
    if skipped["publisher"]:
        toolkit.h.flash_notice(toolkit.ungettext(
            "{count} dataset already had a publisher and kept it.",
            "{count} datasets already had a publisher and kept it.", skipped["publisher"]
        ).format(count=skipped["publisher"]))
    if skipped["contact_point"]:
        toolkit.h.flash_notice(toolkit.ungettext(
            "{count} dataset already had a contact point and kept it.",
            "{count} datasets already had a contact point and kept it.", skipped["contact_point"]
        ).format(count=skipped["contact_point"]))
    for title, message in failures:
        toolkit.h.flash_error(toolkit._("Could not update {title}: {message}").format(title=title, message=message))
    return bool(changed["publisher"] or changed["contact_point"])


ROW_CHOICE = re.compile(r"^(publisher|contact_point)_for_(.+)$")


def _todo_plan(form):
    """What one Save on the To do list sets: ``({dataset id: [publisher id, contact point id]}, ticked ids
    that get nothing)``. Each row's own choices count, and the box's choices go to the ticked rows; a
    row's own choice comes first. The box is the one whose button was pressed, or, without
    JavaScript to keep the two in step, the other one when that one is empty."""
    plan = {}
    for key in form.keys():
        match = ROW_CHOICE.match(key)
        value = (form.get(key) or "").strip()
        if match and value:
            plan.setdefault(match.group(2), ["", ""])[0 if match.group(1) == "publisher" else 1] = value
    pressed = form.get("assign_from", "")
    pressed = pressed if pressed in ("top", "bottom") else "top"
    other = "bottom" if pressed == "top" else "top"
    box = [(form.get(name + pressed) or form.get(name + other) or "").strip()
           for name in ("publisher_actor_id_", "contact_point_id_")]
    left_out = []
    for dataset_id in dict.fromkeys(item for item in form.getlist("dataset_ids") if item):
        choice = plan.setdefault(dataset_id, ["", ""])
        choice[0], choice[1] = choice[0] or box[0], choice[1] or box[1]
        if not any(choice):
            del plan[dataset_id]
            left_out.append(dataset_id)
    return plan, left_out


@blueprint.route("/actor-registry/todo/assign", methods=["POST"])
def todo_assign():
    """Save the To do list (0.6.0): every row's own choices, and the box's choices on the ticked rows.
    Only what a dataset lacks is set (cleanup.assign)."""
    _require_migration_access()
    missing = request.form.get("missing", TODO_DEFAULT)
    if missing not in MISSING_FILTERS:
        missing = TODO_DEFAULT
    try:
        page = max(int(request.form.get("page", "1")), 1)
    except ValueError:
        page = 1
    filters = _todo_filters(request.form)
    plan, left_out = _todo_plan(request.form)
    if not plan:
        toolkit.h.flash_error(toolkit._("Choose in the box what the selected datasets should get.") if left_out else
                              toolkit._("Nothing to save. Choose on a row, or select datasets and choose in the box."))
    else:
        # The rows that get the same are saved together, in the order they came.
        groups = {}
        for dataset_id, choice in plan.items():
            groups.setdefault(tuple(choice), []).append(dataset_id)
        results = []
        for (actor_id, contact_point_id), dataset_ids in groups.items():
            try:
                results.append(cleanup.assign(g.user, dataset_ids, actor_id, contact_point_id))
            except cleanup.CleanupError as error:
                toolkit.h.flash_error(str(error))
        if _flash_assignments(results):
            toolkit.h.flash_notice(toolkit._("A dataset that no longer lacks what this list shows leaves it."))
        if left_out:
            toolkit.h.flash_notice(toolkit.ungettext(
                "{count} selected dataset got nothing: nothing was chosen in the box.",
                "{count} selected datasets got nothing: nothing was chosen in the box.", len(left_out)
            ).format(count=len(left_out)))
    return redirect(_todo_url(missing, filters, page=page, _anchor="todo-list"))


@blueprint.route("/actors/new", methods=["GET", "POST"])
def actors_new():
    _require_login()
    values = _actor_values()
    translations = _translation_values(with_description=True)
    if request.method == "POST" and values["name"]:
        item_id = str(uuid.uuid4())
        values["uri"] = values["uri"] or toolkit.url_for("actor_registry.actors_show", item_id=item_id, _external=True, locale="default")
        identifier_error = _actor_error(values) or _translation_error(translations)
        if identifier_error:
            toolkit.h.flash_error(identifier_error)
        elif _registry_uri_conflict(values["uri"]):
            toolkit.h.flash_error(toolkit._("The URI is already used by a publisher or contact point."))
        else:
            item = Actor(id=item_id, **values)
            item.set_translations(translations or {})
            if _commit(item, toolkit._("The URI is already used by a publisher.")):
                toolkit.h.flash_success(toolkit._("The publisher has been created."))
                return redirect(toolkit.url_for("actor_registry.actors_index"))
    elif request.method == "POST":
        toolkit.h.flash_error(toolkit._("Name is required."))
    return toolkit.render("actor_registry/actor_form.html", extra_vars={
        "item": values, "is_new": True, "languages": _translation_languages(), "translations": translations or {}})


@blueprint.route("/actors/quick-create", methods=["POST"])
def actors_quick_create():
    _require_login()
    values = _actor_values()
    if not values["name"]:
        return jsonify({"success": False, "error": toolkit._("Name is required.")}), 400
    item_id = str(uuid.uuid4())
    values["uri"] = values["uri"] or toolkit.url_for("actor_registry.actors_show", item_id=item_id, _external=True, locale="default")
    values["active"] = True
    identifier_error = _actor_error(values)
    if identifier_error:
        return jsonify({"success": False, "error": identifier_error}), 409
    if _registry_uri_conflict(values["uri"]):
        return jsonify({"success": False, "error": toolkit._("The URI is already used by a publisher or contact point.")}), 409
    translations = _translation_values(with_description=True)
    translation_error = _translation_error(translations)
    if translation_error:
        return jsonify({"success": False, "error": translation_error}), 400
    item = Actor(id=item_id, **values)
    item.set_translations(translations or {})
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
    translations = _translation_values(item, with_description=True)
    translation_error = _translation_error(translations)
    if translation_error:
        return jsonify({"success": False, "error": translation_error}), 400
    for key, value in values.items():
        setattr(item, key, value)
    if translations is not None:
        item.set_translations(translations)
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
    translations = None
    if request.method == "POST":
        values = _actor_values(item)
        translations = _translation_values(item, with_description=True)
        if not values["name"]:
            toolkit.h.flash_error(toolkit._("Name is required."))
        else:
            identifier_error = _actor_error(values, item) or _translation_error(translations)
            has_conflict = bool(identifier_error) or bool(_registry_uri_conflict(values["uri"], item))
            if identifier_error:
                toolkit.h.flash_error(identifier_error)
            elif has_conflict:
                toolkit.h.flash_error(toolkit._("The URI is already used by a publisher or contact point."))
            else:
                for key, value in values.items():
                    setattr(item, key, value)
                if translations is not None:
                    item.set_translations(translations)
            if not has_conflict and _commit(item, toolkit._("The URI is already used by a publisher.")):
                toolkit.h.flash_success(toolkit._("The publisher has been updated."))
                return redirect(toolkit.url_for("actor_registry.actors_index"))
    return toolkit.render("actor_registry/actor_form.html", extra_vars={
        "item": item, "is_new": False, "languages": _translation_languages(item),
        "translations": _form_translations(item, translations)})


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

    owned_contact_points = registry_model.by_display_name(
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
            values_a, values_b = _merge_values(actor_a), _merge_values(actor_b)
            chosen = {}
            for field_name in _merge_fields(actor_a, actor_b):
                override = request.form.get("override_" + field_name, "").strip()
                if override:
                    chosen[field_name] = override
                else:
                    side = request.form.get("field_" + field_name)
                    chosen[field_name] = (values_b if side == "b" else values_a).get(field_name) or ""
            fields = {name: chosen[name] for name in MERGEABLE_FIELDS}
            translations = {}
            for field_name, value in chosen.items():
                if "@" in field_name:
                    key, lang = field_name.split("@", 1)
                    translations.setdefault(lang, {})[key] = value
            try:
                toolkit.get_action("actor_registry_actor_merge")(
                    {"user": g.user},
                    {"keep_id": keep_id, "merge_id": merge_id, "fields": fields, "translations": translations},
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
            "fields": _merge_fields(actor_a, actor_b),
            "values_a": _merge_values(actor_a),
            "values_b": _merge_values(actor_b),
            "field_labels": _merge_field_labels(actor_a, actor_b),
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


# --- Migrate to Actor Registry (step 1: contact points) ---------------------------------
# Editors migrate the datasets they may edit; sysadmins all. See
# contact_migration.py for the rules.

MIGRATION_PAGE_SIZE = 20
# A candidate with more datasets than this is shown compactly (see migrate.html).
MIGRATION_LARGE_GROUP = 25


def _require_migration_access():
    _require_login()
    if not contact_migration.can_migrate(g.user):
        abort(403)


@blueprint.route("/actor-registry/migrate", strict_slashes=False)
def migrate_index():
    _require_migration_access()
    data = contact_migration.survey(g.user)
    helpers.prime_counts(migration=data["counts"])
    total = len(data["candidates"])
    # After the last group of the last page is linked, that page no longer exists: show the new last one.
    page = min(_page_number(), max(1, -(-total // MIGRATION_PAGE_SIZE)))
    start = (page - 1) * MIGRATION_PAGE_SIZE
    pager = Page(
        collection=[], page=page, item_count=total, items_per_page=MIGRATION_PAGE_SIZE,
        url=lambda **kw: toolkit.url_for("actor_registry.migrate_index", **kw),
    )
    return toolkit.render("actor_registry/migrate.html", extra_vars={
        "data": data,
        "candidates": data["candidates"][start:start + MIGRATION_PAGE_SIZE],
        "first_number": start + 1,
        "large_group": MIGRATION_LARGE_GROUP,
        "pager": pager,
        "all_contact_points": all_contact_points(),
        # With only skipped datasets left, they are what the page is for: shown at once.
        "show_skipped": request.args.get("show_skipped") == "1" or (
            not data["counts"]["remaining"] and bool(data["counts"]["skipped"])),
        "closed": contact_migration.is_closed(),
        "tabs": _contact_point_tabs(),
        "close_check": contact_migration.close_check(g.user) if authz.is_sysadmin(g.user) else None,
    })


@blueprint.route("/actor-registry/migrate/apply", methods=["POST"], strict_slashes=False)
def migrate_apply():
    _require_migration_access()
    action = request.form.get("action", "")
    try:
        done, failures, contact_point = contact_migration.apply(
            g.user, action, request.form.getlist("dataset_ids"),
            name=request.form.get("name", ""), email=request.form.get("email", ""),
            contact_point_id=request.form.get("contact_point_id", ""),
            group_key=request.form.get("group_key", ""), exclude_ids=request.form.getlist("exclude_ids"),
        )
    except contact_migration.MigrationError as error:
        toolkit.h.flash_error(str(error))
    else:
        if action == "skip":
            toolkit.h.flash_success(toolkit.ungettext(
                "{count} dataset skipped.", "{count} datasets skipped.", len(done)
            ).format(count=len(done)))
        elif done:
            toolkit.h.flash_success(toolkit.ungettext(
                "{count} dataset linked to {name}.", "{count} datasets linked to {name}.", len(done)
            ).format(count=len(done), name=contact_point.display_name))
        for title, message in failures:
            toolkit.h.flash_error(toolkit._("Could not link {title}: {message}").format(title=title, message=message))
    page = request.form.get("page", "1")
    return redirect(toolkit.url_for("actor_registry.migrate_index", page=page if page.isdigit() else 1))


@blueprint.route("/actor-registry/migrate/unskip", methods=["POST"], strict_slashes=False)
def migrate_unskip():
    _require_migration_access()
    if contact_migration.unskip(g.user, request.form.get("dataset_id", "")):
        toolkit.h.flash_success(toolkit._("The dataset is back among the remaining ones."))
    return redirect(toolkit.url_for("actor_registry.migrate_index", show_skipped=1))


@blueprint.route("/actor-registry/migrate/close", methods=["POST"], strict_slashes=False)
def migrate_close():
    _require_sysadmin()
    try:
        contact_migration.set_closed(g.user, True, confirmed=request.form.get("confirm") == "1")
    except contact_migration.MigrationError as error:
        toolkit.h.flash_error(str(error))
    else:
        toolkit.h.flash_success(toolkit._(
            "The migration is closed. The old contact fields are hidden and no longer exported."))
    return redirect(toolkit.url_for("actor_registry.migrate_index") + "#close")


@blueprint.route("/actor-registry/migrate/reopen", methods=["POST"], strict_slashes=False)
def migrate_reopen():
    _require_sysadmin()
    contact_migration.set_closed(g.user, False)
    toolkit.h.flash_success(toolkit._(
        "The migration is open again. The old contact fields are shown and exported as before."))
    return redirect(toolkit.url_for("actor_registry.migrate_index") + "#close")


# --- Clean-up: inactive or missing records still used by datasets -----------------------


@blueprint.route("/actor-registry/cleanup", strict_slashes=False)
def cleanup_index():
    _require_migration_access()
    data = cleanup.survey(g.user)
    helpers.prime_counts(cleanup=sum(len(data[key]) for key in ("publishers", "contact_points", "missing")))
    return toolkit.render("actor_registry/cleanup.html", extra_vars={
        "data": data,
        "actors": all_actors(),
        "contact_points": all_contact_points(),
        "is_sysadmin": authz.is_sysadmin(g.user),
        "tabs": _todo_tabs(),
    })


@blueprint.route("/actor-registry/cleanup/replace", methods=["POST"], strict_slashes=False)
def cleanup_replace():
    _require_migration_access()
    try:
        changed, failures = cleanup.replace(
            g.user, request.form.get("kind", ""), request.form.get("old_id", ""),
            request.form.get("new_id", ""))
    except cleanup.CleanupError as error:
        toolkit.h.flash_error(str(error))
    else:
        if changed:
            toolkit.h.flash_success(toolkit.ungettext(
                "{count} dataset updated.", "{count} datasets updated.", len(changed)
            ).format(count=len(changed)))
        for title, message in failures:
            toolkit.h.flash_error(toolkit._("Could not update {title}: {message}").format(
                title=title, message=message))
    return redirect(toolkit.url_for("actor_registry.cleanup_index"))
