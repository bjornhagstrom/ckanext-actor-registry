"""A record's own URI does not depend on the language of the page it was created on (0.6.0).

Before, a publisher created on a Swedish page got ``…/sv/actors/<id>`` as its URI, and that
address went into every export, while one created on the default language got none."""

import pytest

from ckan.tests import factories

from ckanext.actor_registry import model

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry"),
    pytest.mark.usefixtures("with_plugins", "actor_registry_db"),
]


@pytest.mark.parametrize("path, key, getter, show", [
    ("/sv/actors/quick-create", "actor", model.get_actor, "/actors/"),
    ("/sv/contactpoints/quick-create", "contact_point", model.get_contact_point, "/contactpoints/"),
])
def test_a_record_created_on_a_swedish_page_gets_a_uri_without_the_language(app, path, key, getter, show):
    headers = {"Authorization": factories.SysadminWithToken()["token"]}
    response = app.post(path, data={"name": "Ny"}, headers=headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    item_id = response.json[key]["id"]
    uri = getter(item_id).uri
    assert "/sv/" not in uri
    assert uri.endswith(f"{show}{item_id}")


def test_the_full_form_on_a_swedish_page_gives_a_uri_without_the_language(app):
    from bs4 import BeautifulSoup
    headers = {"Authorization": factories.SysadminWithToken()["token"]}
    form = BeautifulSoup(app.get("/sv/actors/new", headers=headers).get_data(as_text=True), "html.parser")
    token = form.select_one('input[name="_csrf_token"]')["value"]
    app.post("/sv/actors/new", data={"_csrf_token": token, "name": "Från formuläret", "active": "on"}, headers=headers)
    item = next(actor for actor in model.all_actors() if actor.name == "Från formuläret")
    assert "/sv/" not in item.uri and item.uri.endswith(f"/actors/{item.id}")
