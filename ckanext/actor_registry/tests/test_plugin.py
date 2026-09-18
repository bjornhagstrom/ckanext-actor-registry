from types import SimpleNamespace

from ckanext.actor_registry.plugin import ActorRegistryPlugin


def test_dataset_save_remembers_choices_for_authenticated_user(monkeypatch):
    remembered = {}
    monkeypatch.setattr(
        "ckanext.actor_registry.plugin.model.remember_publisher",
        lambda user_id, actor_id: remembered.update(
            {"publisher": (user_id, actor_id)}
        ),
    )
    monkeypatch.setattr(
        "ckanext.actor_registry.plugin.model.remember_contact_points",
        lambda user_id, contact_ids: remembered.update(
            {"contacts": (user_id, contact_ids)}
        ),
    )

    ActorRegistryPlugin().after_dataset_create(
        {"auth_user_obj": SimpleNamespace(id="user-1")},
        {
            "publisher_actor_id": "actor-1",
            "contact_point_ids": ["contact-1", "contact-2"],
        },
    )

    assert remembered == {
        "publisher": ("user-1", "actor-1"),
        "contacts": ("user-1", ["contact-1", "contact-2"]),
    }
