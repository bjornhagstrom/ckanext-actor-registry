from types import SimpleNamespace

from ckanext.actor_registry import model


def test_registry_uri_owner_checks_both_entity_types(monkeypatch):
    monkeypatch.setattr(
        model, "get_actor_by_uri", lambda uri: SimpleNamespace(id="actor-1")
    )
    monkeypatch.setattr(model, "get_contact_point_by_uri", lambda uri: None)
    assert model.registry_uri_owner("https://example.org/shared") == "actor"

    monkeypatch.setattr(model, "get_actor_by_uri", lambda uri: None)
    monkeypatch.setattr(
        model,
        "get_contact_point_by_uri",
        lambda uri: SimpleNamespace(id="contact-1"),
    )
    assert model.registry_uri_owner("https://example.org/shared") == "contact_point"


def test_registry_uri_owner_allows_current_record_on_edit(monkeypatch):
    monkeypatch.setattr(
        model, "get_actor_by_uri", lambda uri: SimpleNamespace(id="actor-1")
    )
    monkeypatch.setattr(model, "get_contact_point_by_uri", lambda uri: None)

    assert (
        model.registry_uri_owner(
            "https://example.org/actor/1", exclude_actor_id="actor-1"
        )
        is None
    )


def test_registry_uri_owner_ignores_empty_value(monkeypatch):
    monkeypatch.setattr(
        model,
        "get_actor_by_uri",
        lambda uri: (_ for _ in ()).throw(AssertionError("database queried")),
    )
    assert model.registry_uri_owner("") is None
