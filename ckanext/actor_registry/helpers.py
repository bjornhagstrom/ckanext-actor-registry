import json

from flask import g

from ckanext.actor_registry import model
from ckanext.actor_registry.rdf import telephone_uri


def contactpoints_choices(field=None):
    return [
        {"value": item.id, "label": item.name}
        for item in model.all_contact_points()
    ]


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
    if not ids:
        return []
    if isinstance(ids, str):
        ids = [ids]
    return [item.as_dict() for contact_id in ids if (item := model.get_contact_point(contact_id))]


def actors_choices(field=None):
    return [{"value": item.id, "label": item.name} for item in model.all_actors()]


def actors_resolve(ids):
    if not ids:
        return []
    if isinstance(ids, str):
        ids = [ids]
    return [item.as_dict() for actor_id in ids if (item := model.get_actor(actor_id))]


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
    """Resolve a dataset's publisher for public display, or None.

    A merged (soft-retired) actor is followed to the actor it was merged
    into, so old dataset references keep showing a sensible publisher.
    Missing references and retired actors without a merge target yield
    None -- the display snippet then renders nothing rather than a raw id.
    """
    seen = set()
    actor = model.get_actor(actor_id) if actor_id else None
    while actor and not actor.active and actor.merged_into_id and actor.id not in seen:
        seen.add(actor.id)
        actor = model.get_actor(actor.merged_into_id)
    if not actor or not actor.active:
        return None
    return actor.as_dict()


def contactpoints_display(ids):
    """Resolve a dataset's contact points for public display.

    Missing and deactivated contact points are skipped; never returns ids.
    """
    resolved = []
    for contact_id in _id_list(ids):
        item = model.get_contact_point(contact_id)
        if item and item.active:
            resolved.append(item.as_dict())
    return resolved


def preferred_publisher_actor_id():
    user = getattr(g, "userobj", None)
    actor = model.preferred_publisher(getattr(user, "id", None))
    return actor.id if actor else ""


def contactpoints_tel_uri(phone):
    return telephone_uri(phone)
