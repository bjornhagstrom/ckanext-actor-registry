import json
from datetime import datetime, timedelta

import pytest

from ckan import model as ckan_model
from ckan.tests import factories, helpers
from ckanext.actor_registry import model


pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry"),
    pytest.mark.usefixtures("with_plugins", "actor_registry_db"),
]


def _actor(identifier, name, active=True):
    item = model.Actor(
        id=identifier,
        name=name,
        actor_kind="organization",
        uri=f"https://example.org/actor/{identifier}",
        active=active,
    )
    ckan_model.Session.add(item)
    ckan_model.Session.flush()
    return item


def _contact(identifier, name, active=True):
    item = model.ContactPoint(
        id=identifier,
        name=name,
        uri=f"https://example.org/contact/{identifier}",
        active=active,
    )
    ckan_model.Session.add(item)
    ckan_model.Session.flush()
    return item


def test_active_choices_are_alphabetical_and_inactive_are_hidden():
    _actor("z", "Övre bolaget")
    _actor("a", "Alfa nämnd")
    _actor("hidden", "Dold nämnd", active=False)
    _contact("z", "Öppen data")
    _contact("a", "Allmän kontakt")
    _contact("hidden", "Dold kontakt", active=False)

    assert [item.name for item in model.all_actors()] == [
        "Alfa nämnd",
        "Övre bolaget",
    ]
    assert [item.name for item in model.all_contact_points()] == [
        "Allmän kontakt",
        "Öppen data",
    ]


def test_preferred_publisher_must_still_be_active():
    actor = _actor("publisher", "Utgivare")
    model.remember_publisher("user-1", actor.id)
    assert model.preferred_publisher("user-1").id == actor.id

    actor.active = False
    ckan_model.Session.flush()
    assert model.preferred_publisher("user-1") is None


def test_recent_contacts_are_ordered_and_limited():
    contacts = [_contact(str(index), f"Kontakt {index}") for index in range(4)]
    base = datetime.utcnow()
    for index, contact in enumerate(contacts):
        ckan_model.Session.add(
            model.RecentContactPoint(
                user_id="user-1",
                contact_point_id=contact.id,
                used_at=base + timedelta(minutes=index),
            )
        )
    ckan_model.Session.flush()

    assert [item.id for item in model.recent_contact_points("user-1", limit=3)] == [
        "3",
        "2",
        "1",
    ]


def test_actor_and_contact_cannot_share_uri_at_application_level():
    actor = _actor("publisher", "Utgivare")
    contact = _contact("contact", "Kontakt")

    assert model.registry_uri_owner(actor.uri) == "actor"
    assert model.registry_uri_owner(contact.uri) == "contact_point"
    assert (
        model.registry_uri_owner(actor.uri, exclude_actor_id=actor.id) is None
    )


def _set_extras(package_id, extras):
    """Write package.extras directly (a jsonb column, verified empirically
    against the -dev stack -- see aktorsregister-sammanslagning-plan.md),
    bypassing the extras-list/scheming validator pipeline so this test
    only exercises datasets_for_actor()'s own SQL, not extras validation.
    """
    package = ckan_model.Package.get(package_id)
    package.extras = extras
    ckan_model.Session.add(package)
    ckan_model.Session.commit()


def test_datasets_for_actor_splits_publisher_and_contact_point_links():
    actor = _actor("publisher-actor", "Utgivarnämnden")
    other_actor = _actor("other-actor", "Annan nämnd")
    contact = _contact("contact", "Kontaktcenter")
    contact.actor_id = actor.id
    ckan_model.Session.flush()

    organization = factories.Organization()
    published = factories.Dataset(owner_org=organization["id"])
    _set_extras(published["id"], {"publisher_actor_id": actor.id})

    contacted = factories.Dataset(owner_org=organization["id"])
    _set_extras(
        contacted["id"], {"contact_point_ids": json.dumps([contact.id])}
    )

    unrelated = factories.Dataset(owner_org=organization["id"])
    _set_extras(unrelated["id"], {"publisher_actor_id": other_actor.id})

    linked = model.datasets_for_actor(actor.id)

    assert linked["publisher"] == [published["id"]]
    assert linked["contact_point"] == [contacted["id"]]
    assert unrelated["id"] not in linked["publisher"]
    assert unrelated["id"] not in linked["contact_point"]


def test_datasets_for_actor_decodes_double_encoded_contact_point_list():
    actor = _actor("multi-contact-actor", "Nämnd med flera kontaktpunkter")
    contact_a = _contact("contact-a", "Kontakt A")
    contact_b = _contact("contact-b", "Kontakt B")
    contact_a.actor_id = actor.id
    contact_b.actor_id = actor.id
    ckan_model.Session.flush()

    organization = factories.Organization()
    dataset = factories.Dataset(owner_org=organization["id"])
    # Matches ckanext-scheming's real multiple_select serialisation for
    # contact_point_ids: a JSON string whose *content* is itself a
    # JSON-encoded list (verified against the -dev stack, see
    # aktorsregister-sammanslagning-plan.md), not a plain jsonb array.
    _set_extras(
        dataset["id"],
        {"contact_point_ids": json.dumps([contact_a.id, contact_b.id])},
    )

    assert model.datasets_for_actor(actor.id)["contact_point"] == [dataset["id"]]


def test_datasets_for_actor_ignores_deleted_datasets():
    actor = _actor("actor-with-deleted-dataset", "Nämnd med raderad datamängd")
    organization = factories.Organization()
    sysadmin = factories.Sysadmin()
    dataset = factories.Dataset(owner_org=organization["id"])
    _set_extras(dataset["id"], {"publisher_actor_id": actor.id})

    helpers.call_action(
        "package_delete", context={"user": sysadmin["name"]}, id=dataset["id"]
    )

    assert model.datasets_for_actor(actor.id) == {"publisher": [], "contact_point": []}


def test_datasets_for_actor_returns_empty_lists_for_actor_without_datasets():
    actor = _actor("lonely-actor", "Nämnd utan kopplingar")
    assert model.datasets_for_actor(actor.id) == {"publisher": [], "contact_point": []}


def test_datasets_without_actor_link_finds_datasets_missing_both_fields():
    organization = factories.Organization()
    actor = _actor("linking-actor", "Nämnd med koppling")

    unlinked = factories.Dataset(owner_org=organization["id"])
    # No _set_extras call at all -- mirrors a dataset that predates the
    # actor-registry extension being activated (no publisher_actor_id or
    # contact_point_ids key in extras whatsoever).

    with_publisher = factories.Dataset(owner_org=organization["id"])
    _set_extras(with_publisher["id"], {"publisher_actor_id": actor.id})

    contact = _contact("linking-contact", "Kontakt")
    contact.actor_id = actor.id
    ckan_model.Session.flush()
    with_contact_point = factories.Dataset(owner_org=organization["id"])
    _set_extras(
        with_contact_point["id"], {"contact_point_ids": json.dumps([contact.id])}
    )

    result = model.datasets_without_actor_link()

    assert unlinked["id"] in result
    assert with_publisher["id"] not in result
    assert with_contact_point["id"] not in result


def test_datasets_without_actor_link_treats_blank_values_as_missing():
    organization = factories.Organization()
    dataset = factories.Dataset(owner_org=organization["id"])
    # Blank publisher_actor_id and an empty (double-encoded) contact_point_ids
    # list -- both scheming presets can leave keys like this rather than
    # omitting them entirely, so both must still count as "unlinked".
    _set_extras(
        dataset["id"],
        {"publisher_actor_id": "", "contact_point_ids": json.dumps([])},
    )

    assert dataset["id"] in model.datasets_without_actor_link()


def test_datasets_without_actor_link_ignores_deleted_datasets():
    organization = factories.Organization()
    sysadmin = factories.Sysadmin()
    dataset = factories.Dataset(owner_org=organization["id"])

    helpers.call_action(
        "package_delete", context={"user": sysadmin["name"]}, id=dataset["id"]
    )

    assert dataset["id"] not in model.datasets_without_actor_link()
