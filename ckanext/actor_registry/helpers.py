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


def preferred_publisher_actor_id():
    user = getattr(g, "userobj", None)
    actor = model.preferred_publisher(getattr(user, "id", None))
    return actor.id if actor else ""


def contactpoints_tel_uri(phone):
    return telephone_uri(phone)
