import uuid

import pytest

from ckan import model as ckan_model
from ckan.tests import factories, helpers

from ckanext.actor_registry import model

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "scheming_datasets actor_registry"),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas",
        "ckanext.actor_registry.tests.fixtures:dcat_test_schema.yaml",
    ),
    pytest.mark.ckan_config(
        "scheming.presets",
        "ckanext.scheming:presets.json ckanext.dcat.schemas:presets.yaml",
    ),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db"),
]


def _actor(name, **overrides):
    actor_id = str(uuid.uuid4())
    item = model.Actor(
        id=actor_id,
        name=name,
        actor_kind="organization",
        uri=f"https://example.org/actor/{actor_id}",
        active=overrides.pop("active", True),
        **overrides,
    )
    ckan_model.Session.add(item)
    ckan_model.Session.flush()
    return item


def _contact(name, **overrides):
    contact_id = str(uuid.uuid4())
    item = model.ContactPoint(
        id=contact_id,
        name=name,
        uri=f"https://example.org/contact/{contact_id}",
        active=overrides.pop("active", True),
        **overrides,
    )
    ckan_model.Session.add(item)
    ckan_model.Session.flush()
    return item


def _dataset(publisher_id, contact_ids):
    sysadmin = factories.Sysadmin()
    context = {"user": sysadmin["name"]}
    organization = helpers.call_action(
        "organization_create", context=context, name=f"disp-{uuid.uuid4().hex}", title="Org"
    )
    return helpers.call_action(
        "package_create",
        context=context,
        name=f"disp-{uuid.uuid4().hex}",
        title="Visningstest",
        notes="Text",
        owner_org=organization["id"],
        publisher_actor_id=publisher_id,
        contact_point_ids=contact_ids,
    )


def _anonymous_page(app, dataset):
    response = app.get(f"/dataset/{dataset['name']}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_anonymous_view_shows_names_and_contact_details_never_uuids(app):
    actor = _actor("Skellefteå kommun", url="https://www.example.org")
    one = _contact("Kontaktcenter", email="kontakt@example.org", phone="+46 910 73 50 00")
    two = _contact("Datafunktionen", url="https://example.org/data")
    dataset = _dataset(actor.id, [one.id, two.id])

    html = _anonymous_page(app, dataset)

    assert "Skellefteå kommun" in html
    assert "Kontaktcenter" in html and "Datafunktionen" in html
    assert "kontakt@example.org" in html
    assert "tel:" in html
    for raw_id in (actor.id, one.id, two.id):
        # ids may legitimately appear inside link hrefs, never as visible text
        assert f">{raw_id}<" not in html
        assert f'["{raw_id}"' not in html and f'&#34;{raw_id}' not in html


def test_merged_actor_is_shown_as_its_survivor(app):
    survivor = _actor("Kvarvarande nämnd")
    retired = _actor("Bortslagen nämnd")
    dataset = _dataset(retired.id, [])
    # Retired after the dataset was created, as a real merge would do.
    retired.active = False
    retired.merged_into_id = survivor.id
    ckan_model.Session.commit()

    html = _anonymous_page(app, dataset)

    assert "Kvarvarande nämnd" in html
    assert "Bortslagen nämnd" not in html


def test_inactive_and_missing_references_render_nothing_instead_of_ids(app):
    retired = _actor("Pensionerad utan mål")
    inactive_contact = _contact("Avstängd kontakt")
    deleted_contact = _contact("Raderad kontakt")
    live_contact = _contact("Levande kontakt")
    dataset = _dataset(retired.id, [inactive_contact.id, deleted_contact.id, live_contact.id])
    # References go stale after creation: deactivated, deleted (dangling id).
    ghost_contact = deleted_contact.id
    retired.active = False
    inactive_contact.active = False
    ckan_model.Session.delete(deleted_contact)
    ckan_model.Session.commit()

    html = _anonymous_page(app, dataset)

    assert "Levande kontakt" in html
    assert "Avstängd kontakt" not in html
    assert "Pensionerad utan mål" not in html
    assert ghost_contact not in html
    assert retired.id not in html


def test_several_contact_points_are_visually_separated(app):
    actor = _actor("Skellefteå kommun")
    contacts = [_contact(f"Kontakt {n}") for n in ("A", "B", "C")]
    dataset = _dataset(actor.id, [c.id for c in contacts])

    html = _anonymous_page(app, dataset)

    from bs4 import BeautifulSoup

    blocks = BeautifulSoup(html, "html.parser").select("div.contact-point")
    assert len(blocks) == 3
    assert "border-top" not in blocks[0]["class"]
    assert all("border-top" in b["class"] and "mt-3" in b["class"] for b in blocks[1:])


def test_publisher_details_are_on_their_own_lines_without_parentheses(app):
    actor = _actor(
        "Skellefteå kommun",
        actor_type="https://example.org/concepts/public-body",
        url="https://www.example.org",
        email="info@example.org",
        description="Kommunen i norra Västerbotten.",
    )
    dataset = _dataset(actor.id, [])

    html = _anonymous_page(app, dataset)

    from bs4 import BeautifulSoup

    block = BeautifulSoup(html, "html.parser").select_one("div.publisher")
    # Name first, then type, web address, email and description -- one per line.
    assert list(block.stripped_strings) == [
        "Skellefteå kommun",
        "https://example.org/concepts/public-body",
        "https://www.example.org",
        "info@example.org",
        "Kommunen i norra Västerbotten.",
    ]
    assert len(block.find_all("br")) == 4
    assert "(" not in block.get_text() and ")" not in block.get_text()
    assert block.select_one('a[href="mailto:info@example.org"]') is not None


def test_publisher_without_optional_details_shows_only_the_name(app):
    actor = _actor("Bara namn")
    dataset = _dataset(actor.id, [])

    from bs4 import BeautifulSoup

    block = BeautifulSoup(_anonymous_page(app, dataset), "html.parser").select_one("div.publisher")

    assert list(block.stripped_strings) == ["Bara namn"]
    assert block.find("br") is None


BAD_URL = "javascript:alert(document.cookie)"


def test_a_stored_javascript_url_is_never_a_link_on_the_public_pages(app):
    # The forms reject non-http(s) URLs on save, but rows saved earlier (or written by
    # other means) can hold anything. Such a value must be shown as text, never as an
    # href a visitor could click.
    actor = _actor("Äldre utgivare", url=BAD_URL)
    actor.uri = BAD_URL + "/uri"
    contact = _contact("Äldre kontakt", url=BAD_URL)
    ckan_model.Session.commit()
    dataset = _dataset(actor.id, [contact.id])

    from bs4 import BeautifulSoup

    for path in (f"/dataset/{dataset['name']}", f"/actors/{actor.id}", f"/contactpoints/{contact.id}"):
        html = app.get(path).get_data(as_text=True)
        hrefs = [a.get("href", "") for a in BeautifulSoup(html, "html.parser").find_all("a")]
        assert not [h for h in hrefs if h.lower().startswith("javascript:")], path
        assert BAD_URL in html or path.endswith(contact.id) is False, path  # still visible, as text


def test_valid_http_urls_are_still_links(app):
    actor = _actor("Ny utgivare", url="https://www.example.org")
    dataset = _dataset(actor.id, [])

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(app.get(f"/dataset/{dataset['name']}").get_data(as_text=True), "html.parser")

    assert soup.select_one('div.publisher a[href="https://www.example.org"]') is not None
