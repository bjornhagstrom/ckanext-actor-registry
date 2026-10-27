import json

from flask import g
from markupsafe import Markup

import ckan.plugins.toolkit as toolkit

from ckanext.actor_registry import model
from ckanext.actor_registry.rdf import telephone_uri


def contactpoints_choices(field=None):
    # Inactive contact points are valid choices for Scheming, so a dataset that
    # already has one can still be saved; actor_registry_contactpoints_exist
    # stops new use of them, with a message that names them.
    return [
        {"value": item.id, "label": item.name}
        for item in model.all_contact_points(include_inactive=True)
    ]


def contactpoints_unavailable(selected):
    """The selected contact points the form cannot offer as normal choices:
    ``{"id", "name", "state"}`` with state ``inactive`` or ``missing``."""
    result = []
    for contact_id in _id_list(selected):
        item = model.get_contact_point(contact_id)
        if item is None:
            result.append({"id": contact_id, "name": "", "state": "missing"})
        elif not item.active:
            result.append({"id": contact_id, "name": item.name, "state": "inactive"})
    return result


def contactpoints_grouped_choices():
    user = getattr(g, "userobj", None)
    recent = model.recent_contact_points(getattr(user, "id", None), limit=3)
    recent_ids = {item.id for item in recent}
    return {
        "recent": [item.as_dict() for item in recent],
        "alphabetical": [
            item.as_dict() for item in model.all_contact_points() if item.id not in recent_ids
        ],
    }


def contactpoints_resolve(ids):
    return [item.as_dict() for contact_id in _id_list(ids) if (item := model.get_contact_point(contact_id))]


def actors_choices(field=None):
    # Inactive publishers are valid choices for Scheming, so a dataset that
    # already has one can still be saved; actor_registry_actor_exists stops
    # new use of them. The form lists only active ones.
    return [{"value": item.id, "label": item.name} for item in model.all_actors(include_inactive=True)]


def active_actors_choices():
    """Active publishers only, for pickers that offer new choices."""
    return [{"value": item.id, "label": item.name} for item in model.all_actors()]


def actor_unavailable(selected):
    """The selected publisher if the form cannot offer it as a normal choice:
    ``{"id", "name", "state"}`` with state ``inactive`` or ``missing``, or None."""
    if not selected:
        return None
    item = model.get_actor(selected)
    if item is None:
        return {"id": selected, "name": "", "state": "missing"}
    if not item.active:
        return {"id": selected, "name": item.name, "state": "inactive"}
    return None


def actors_resolve(ids):
    return [item.as_dict() for actor_id in _id_list(ids) if (item := model.get_actor(actor_id))]


def _id_list(value):
    """Normalise a stored multi-value field (list, JSON string or bare id)."""
    if not value:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                value = json.loads(stripped)
            except ValueError:
                return []
        else:
            value = [stripped]
    return [str(item) for item in value if item]


def actor_display(actor_id):
    """The publisher a dataset shows AND exports (the DCAT profile uses this
    too: what visitors see is what is exported), or None.

    A merged publisher is followed to the one it was merged into. An inactive
    publisher is still the dataset's publisher until someone replaces it, so
    it is shown and exported. A missing reference yields None (the DCAT export
    then falls back to the organization).
    """
    seen = set()
    actor = model.get_actor(actor_id) if actor_id else None
    while actor and not actor.active and actor.merged_into_id and actor.id not in seen:
        seen.add(actor.id)
        target = model.get_actor(actor.merged_into_id)
        if target is None:
            break
        actor = target
    return actor.as_dict() if actor else None


def contactpoints_display(ids):
    """The contact points a dataset shows AND exports (see actor_display).

    An inactive contact point stays until someone replaces it, so it is shown
    and exported; missing ones are skipped. Never returns ids.
    """
    return contactpoints_resolve(ids)


def preferred_publisher_actor_id():
    user = getattr(g, "userobj", None)
    actor = model.preferred_publisher(getattr(user, "id", None))
    return actor.id if actor else ""


def contactpoints_tel_uri(phone):
    return telephone_uri(phone)


def can_migrate():
    """Whether the current user may use "Migrate to Actor Registry" (a tab)."""
    from ckanext.actor_registry import contact_migration
    user = getattr(g, "user", None)
    return bool(user) and contact_migration.can_migrate(user)


LEGACY_CONTACT_FIELDS_OPTION = "ckanext.actor_registry.legacy_contact_fields"


def legacy_contact_fields_in_use():
    """Whether CKAN's own contact fields (Maintainer, Author) are still in use.

    False once the migration to the registry is closed: the fields are then
    hidden (in schemas that use the legacy_contact.html snippets) and not
    exported. A declared bool option, also changeable at runtime by "Close
    the migration" (config_option_update), so the value can be a bool, a
    string saved at runtime, or "" (see below).
    """
    value = toolkit.config.get(LEGACY_CONTACT_FIELDS_OPTION, True)
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    # CKAN's app_globals.reset() turns a false ini value into "" when nothing
    # has been saved at runtime, so an empty value means false here. Anything
    # else follows CKAN's rule for booleans (only these words are true).
    return str(value).strip().lower() in ("true", "yes", "t", "y", "1", "on")


def _once_per_request(key, compute):
    """The navigation asks for the same counts on every registry page, and some pages ask twice. The migration and the
    clean-up page hand over what they computed themselves (prime_counts), so those two pages do not survey twice for it."""
    cache = g.__dict__.setdefault("_actor_registry_counts", {})
    if key not in cache:
        cache[key] = compute()
    return cache[key]


def cleanup_count():
    """Entries on the clean-up page for the current user (0 when not allowed)."""
    from ckanext.actor_registry import cleanup, contact_migration
    user = getattr(g, "user", None)
    if not user or not contact_migration.can_migrate(user):
        return 0
    return _once_per_request("cleanup", lambda: cleanup.count(user))


def _migration_waiting(data):
    return data["counts"]["remaining"] + data["counts"]["changed"]


def prime_counts(**counts):
    """A page that has just computed its own survey hands the number to the navigation, which would compute it again."""
    cache = g.__dict__.setdefault("_actor_registry_counts", {})
    cache.update(counts)


def migration_remaining_count():
    """Datasets that still wait to be migrated or that changed since they were linked, for the current user (0 when not allowed)."""
    from ckanext.actor_registry import contact_migration
    user = getattr(g, "user", None)
    if not user or not contact_migration.can_migrate(user):
        return 0
    return _once_per_request("migration", lambda: _migration_waiting(contact_migration.survey(user)))


def nav_item(endpoint, prefix, label, icon, count=0, pills=False):
    """One entry of a navigation. It is active on its own page and on the pages under it (whose endpoint names start
    with ``prefix``), and has a small number next to the label when something waits. ``pills`` makes an entry of
    the submenu (Bootstrap pills) instead of an Administration tab."""
    from flask import request
    active = (request.endpoint or "").startswith(prefix)
    badge = Markup(' <span class="badge text-bg-warning" data-nav-count>{}</span>').format(count) if count else ""
    link = Markup('<i class="fa fa-{}"></i> {}{}').format(icon, label, badge)
    if pills:
        return Markup('<li class="nav-item"><a class="nav-link{}" href="{}"{}>{}</a></li>').format(
            " active" if active else "", toolkit.url_for(endpoint),
            Markup(' aria-current="page"') if active else "", link)
    return Markup('<li{}><a href="{}">{}</a></li>').format(
        Markup(' class="active"') if active else "", toolkit.url_for(endpoint), link)


def admin_tab_enabled():
    """Whether Administration (/ckan-admin) has one tab that leads to the registry."""
    return toolkit.asbool(toolkit.config.get("ckanext.actor_registry.admin_tab", True))
