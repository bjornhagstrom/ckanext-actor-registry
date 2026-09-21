"""Contact point -> "Belongs to organization" (actor_id): admin form, inline
dialog (quick-create / quick-edit) and the public contact point page."""

import uuid

import pytest

from ckan import model as ckan_model
from ckan.tests import factories

from ckanext.actor_registry import model

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry"),
    pytest.mark.ckan_config("ckan.locales_offered", "en sv sv_SE"),
    pytest.mark.usefixtures("with_plugins", "actor_registry_db"),
]


def _headers(user):
    return {"Authorization": user["token"]}


def _actor(name="Skellefteå kommun", active=True):
    actor_id = str(uuid.uuid4())
    ckan_model.Session.add(
        model.Actor(id=actor_id, name=name, actor_kind="organization",
                    uri=f"https://example.org/actor/{actor_id}", active=active)
    )
    ckan_model.Session.commit()
    return actor_id


def _contact(actor_id=None, name="Kontakt B"):
    contact_id = str(uuid.uuid4())
    ckan_model.Session.add(
        model.ContactPoint(id=contact_id, name=name, actor_id=actor_id,
                           uri=f"https://example.org/contact/{contact_id}", active=True)
    )
    ckan_model.Session.commit()
    return contact_id


def test_quick_create_can_set_the_organization(app):
    actor_id = _actor()
    headers = _headers(factories.SysadminWithToken())

    response = app.post("/contactpoints/quick-create", data={"name": "Ny", "actor_id": actor_id}, headers=headers)

    assert response.status_code == 200
    assert response.json["contact_point"]["actor_id"] == actor_id


def test_quick_create_rejects_unknown_or_inactive_organization(app):
    headers = _headers(factories.SysadminWithToken())
    for bad in (str(uuid.uuid4()), _actor("Pensionerad", active=False)):
        response = app.post("/contactpoints/quick-create", data={"name": "Ny", "actor_id": bad}, headers=headers)
        assert response.status_code == 409
        assert "organization" in response.json["error"]


def test_quick_edit_changes_clears_and_preserves_the_organization(app):
    first, second = _actor("Första"), _actor("Andra")
    contact_id = _contact(first)
    headers = _headers(factories.SysadminWithToken())
    url = f"/contactpoints/{contact_id}/quick-edit"

    changed = app.post(url, data={"name": "Kontakt B", "actor_id": second}, headers=headers)
    assert changed.json["contact_point"]["actor_id"] == second

    # A payload WITHOUT actor_id (older client) must not wipe the link.
    kept = app.post(url, data={"name": "Kontakt B"}, headers=headers)
    assert kept.json["contact_point"]["actor_id"] == second

    cleared = app.post(url, data={"name": "Kontakt B", "actor_id": ""}, headers=headers)
    assert cleared.json["contact_point"]["actor_id"] == ""


def test_editing_is_not_blocked_by_an_organization_retired_since(app):
    actor_id = _actor("Ska pensioneras")
    contact_id = _contact(actor_id)
    ckan_model.Session.query(model.Actor).filter_by(id=actor_id).update({"active": False})
    ckan_model.Session.commit()
    headers = _headers(factories.SysadminWithToken())

    response = app.post(
        f"/contactpoints/{contact_id}/quick-edit",
        data={"name": "Nytt namn", "actor_id": actor_id}, headers=headers,
    )

    assert response.status_code == 200


def test_admin_form_has_the_organization_dropdown_with_new_label(app):
    actor_id = _actor()
    contact_id = _contact(actor_id)
    headers = _headers(factories.SysadminWithToken())

    en = app.get(f"/en/contactpoints/{contact_id}/edit", headers=headers).get_data(as_text=True)
    sv = app.get(f"/sv/contactpoints/{contact_id}/edit", headers=headers).get_data(as_text=True)

    assert 'name="actor_id"' in en and f'value="{actor_id}" selected' in en
    assert "Belongs to organization" in en
    assert "Tillhör organisation" in sv and "Tillhör aktör" not in sv


def test_public_page_shows_organization_only_when_set(app):
    actor_id = _actor("Skellefteå kommun")
    linked, unlinked = _contact(actor_id), _contact(None, "Fristående")

    with_org = app.get(f"/sv/contactpoints/{linked}").get_data(as_text=True)
    without = app.get(f"/sv/contactpoints/{unlinked}").get_data(as_text=True)

    assert "Tillhör organisation" in with_org and "Skellefteå kommun" in with_org
    assert "Tillhör organisation" not in without and "Tillhör aktör" not in without



def test_contact_point_list_links_each_name_to_its_page(app):
    # Like the publisher list, so a contact point's page (and the datasets it
    # lists) can be reached from the registry.
    contact_id = _contact(None, "Länkad kontakt")
    headers = _headers(factories.SysadminWithToken())

    html = app.get("/en/contactpoints", headers=headers).get_data(as_text=True)

    assert f'href="/en/contactpoints/{contact_id}"' in html or f'href="/contactpoints/{contact_id}"' in html
