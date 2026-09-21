"""Datasets linked to an actor / contact point: preview, "show all" page,
pagination and visibility. Lists come from the database, never the search
index, so none of these tests depends on Solr being in sync."""

import uuid

import pytest
from bs4 import BeautifulSoup
from sqlalchemy import text

from ckan import model as ckan_model
from ckan.tests import factories, helpers

from ckanext.actor_registry import model

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "scheming_datasets actor_registry"),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas", "ckanext.actor_registry.tests.fixtures:form_schema.yaml"
    ),
    pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json"),
    pytest.mark.ckan_config("ckan.locales_offered", "en sv sv_SE"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db"),
]


def _headers(user):
    return {"Authorization": user["token"]}


def _actor(name="Skellefteå kommun"):
    actor_id = str(uuid.uuid4())
    ckan_model.Session.add(
        model.Actor(id=actor_id, name=name, actor_kind="organization",
                    uri=f"https://example.org/actor/{actor_id}", active=True)
    )
    ckan_model.Session.commit()
    return actor_id


def _contact(actor_id=None, name="Kontakt"):
    contact_id = str(uuid.uuid4())
    ckan_model.Session.add(
        model.ContactPoint(id=contact_id, name=name, actor_id=actor_id,
                           uri=f"https://example.org/contact/{contact_id}", active=True)
    )
    ckan_model.Session.commit()
    return contact_id


@pytest.fixture
def org():
    sysadmin = factories.Sysadmin()
    return helpers.call_action(
        "organization_create", context={"user": sysadmin["name"]},
        name=f"o-{uuid.uuid4().hex}", title="Org",
    )


def _dataset(org, title, private=False, **fields):
    sysadmin = factories.Sysadmin()
    return helpers.call_action(
        "package_create", context={"user": sysadmin["name"]},
        name=f"d-{uuid.uuid4().hex}", title=title, owner_org=org["id"], private=private, **fields,
    )


def _links(html):
    return [a.get_text(strip=True) for a in BeautifulSoup(html, "html.parser").select("ul.dataset-list li a")]


def test_contact_point_page_lists_its_datasets_alphabetically(app, org):
    contact = _contact()
    _dataset(org, "Ö-data", contact_point_ids=[contact])
    _dataset(org, "Alfa", contact_point_ids=[contact])
    _dataset(org, "Ej kopplad")

    html = app.get(f"/contactpoints/{contact}").get_data(as_text=True)

    assert _links(html) == ["Alfa", "Ö-data"]
    assert "Show all" not in html


def test_contact_point_page_says_when_nothing_is_linked(app):
    html = app.get(f"/en/contactpoints/{_contact()}").get_data(as_text=True)

    assert "No dataset is linked to this contact point." in html


def test_actor_page_previews_ten_with_total_and_show_all(app, org):
    actor = _actor()
    for n in range(25):
        _dataset(org, f"Data {n:02d}", publisher_actor_id=actor)

    html = app.get(f"/en/actors/{actor}").get_data(as_text=True)

    assert len(_links(html)) == 10
    assert _links(html)[0] == "Data 00"
    assert "Publisher for 25 dataset(s)" in html
    assert "Show all 25" in html


def test_show_all_page_paginates_twenty_per_page(app, org):
    actor = _actor()
    for n in range(25):
        _dataset(org, f"Data {n:02d}", publisher_actor_id=actor)

    first = app.get(f"/actors/{actor}/datasets?link=publisher").get_data(as_text=True)
    second = app.get(f"/actors/{actor}/datasets?link=publisher&page=2").get_data(as_text=True)

    assert len(_links(first)) == 20 and _links(first)[0] == "Data 00"
    assert _links(second) == [f"Data {n:02d}" for n in range(20, 25)]
    assert "page=2" in first  # the pager links onward


def test_publisher_is_not_treated_as_a_contact_point(app, org):
    # A publisher lists only the datasets it PUBLISHES. Datasets that use a
    # contact point which merely "belongs to" the publisher are not its
    # datasets, and there is no "via contact points" list or page.
    actor = _actor()
    contact = _contact(actor)
    _dataset(org, "Bara via kontakt", contact_point_ids=[contact])
    _dataset(org, "Utgiven", publisher_actor_id=actor)

    page = app.get(f"/en/actors/{actor}").get_data(as_text=True)

    assert _links(page) == ["Utgiven"]
    assert "Bara via kontakt" not in page
    assert "Contact point linked to" not in page
    assert "linked to this publisher" not in page
    assert app.get(f"/actors/{actor}/datasets?link=contact_point").status_code == 404


@pytest.mark.parametrize("url", ["/actors/{a}/datasets?link=bogus", "/actors/{a}/datasets?page=99"])
def test_bad_link_or_page_beyond_the_end_is_404(app, org, url):
    actor = _actor()
    _dataset(org, "En", publisher_actor_id=actor)

    assert app.get(url.format(a=actor)).status_code == 404


def test_non_numeric_page_falls_back_to_first_page(app, org):
    actor = _actor()
    _dataset(org, "En", publisher_actor_id=actor)

    response = app.get(f"/actors/{actor}/datasets?page=abc")

    assert response.status_code == 200
    assert _links(response.get_data(as_text=True)) == ["En"]


# --- Visibility: private datasets must never leak ----------------------------------


def test_private_datasets_are_hidden_from_anonymous_visitors(app, org):
    actor = _actor()
    contact = _contact(actor)
    _dataset(org, "Publik", publisher_actor_id=actor, contact_point_ids=[contact])
    _dataset(org, "Hemlig", private=True, publisher_actor_id=actor, contact_point_ids=[contact])

    for path in (f"/actors/{actor}", f"/actors/{actor}/datasets",
                 f"/contactpoints/{contact}", f"/contactpoints/{contact}/datasets"):
        html = app.get(path).get_data(as_text=True)
        assert "Hemlig" not in html, path
        assert "Publik" in html, path
    assert "Publisher for 1 dataset(s)" in app.get(f"/en/actors/{actor}").get_data(as_text=True)


def test_private_datasets_are_visible_to_org_members_and_sysadmins_only(app, org):
    actor = _actor()
    _dataset(org, "Hemlig", private=True, publisher_actor_id=actor)
    member = factories.UserWithToken()
    outsider = factories.UserWithToken()
    helpers.call_action(
        "organization_member_create", context={"user": factories.Sysadmin()["name"]},
        id=org["id"], username=member["name"], role="member",
    )
    sysadmin = factories.SysadminWithToken()

    seen = {
        who: "Hemlig" in app.get(f"/actors/{actor}", headers=_headers(user)).get_data(as_text=True)
        for who, user in (("member", member), ("outsider", outsider), ("sysadmin", sysadmin))
    }

    assert seen == {"member": True, "outsider": False, "sysadmin": True}


def test_deleted_datasets_are_never_listed(app, org):
    actor = _actor()
    kept = _dataset(org, "Aktiv", publisher_actor_id=actor)
    gone = _dataset(org, "Raderad", publisher_actor_id=actor)
    helpers.call_action("package_delete", context={"user": factories.Sysadmin()["name"]}, id=gone["id"])

    assert _links(app.get(f"/actors/{actor}/datasets").get_data(as_text=True)) == [kept["title"]]


def test_lists_ignore_a_stale_search_index(app, org):
    # A document in Solr that no longer exists in the database must not show
    # up: the lists are read from the database only.
    actor = _actor()
    real = _dataset(org, "Finns", publisher_actor_id=actor)
    ckan_model.Session.execute(
        text("UPDATE package SET title = :title WHERE id = :id"),
        {"title": "Uppdaterad titel", "id": real["id"]},
    )
    ckan_model.Session.commit()

    assert _links(app.get(f"/actors/{actor}/datasets").get_data(as_text=True)) == ["Uppdaterad titel"]


def test_swedish_pages_say_utgivare_not_aktor(app, org):
    actor = _actor()
    contact = _contact(actor)
    _dataset(org, "En", publisher_actor_id=actor)
    headers = _headers(factories.SysadminWithToken())

    for path in (f"/sv/actors/{actor}", f"/sv/actors/{actor}/datasets", f"/sv/actors/{actor}/edit",
                 "/sv/actors", "/sv/actors/new", f"/sv/contactpoints/{contact}"):
        html = app.get(path, headers=headers).get_data(as_text=True)
        assert "aktör" not in html.lower(), path
    assert "Utgivare" in app.get("/sv/actors", headers=headers).get_data(as_text=True)


# --- Delete confirmations ------------------------------------------------------------


def test_actor_delete_confirmation_counts_everything_and_previews_ten(app, org):
    actor = _actor()
    contact = _contact(actor)
    for n in range(12):
        _dataset(org, f"Utgiven {n:02d}", publisher_actor_id=actor)
    _dataset(org, "Hemlig", private=True, publisher_actor_id=actor)
    headers = _headers(factories.SysadminWithToken())

    html = app.get(f"/en/actors/{actor}/delete", headers=headers).get_data(as_text=True)

    assert "13 dataset(s) have this publisher" in html
    assert "reference a contact point" not in html
    # The owned contact point is listed too (it becomes standalone); only count datasets.
    assert "Kontakt" in _links(html)
    listed = [t for t in _links(html) if t != "Kontakt"]
    assert listed.count("Hemlig") == 1  # sysadmin sees private ones
    assert len(listed) == 10
    assert "Show all 13" in html and f"/actors/{actor}/datasets?link=publisher" in html


def test_contactpoint_delete_confirmation_uses_the_database_list(app, org):
    contact = _contact()
    for n in range(11):
        _dataset(org, f"Data {n:02d}", contact_point_ids=[contact])
    headers = _headers(factories.SysadminWithToken())

    html = app.get(f"/en/contactpoints/{contact}/delete", headers=headers).get_data(as_text=True)

    assert "11 dataset(s) list this contact point" in html
    assert len(_links(html)) == 10 and "Show all 11" in html


def test_delete_confirmations_still_work_with_nothing_linked(app):
    actor, contact = _actor(), _contact()
    headers = _headers(factories.SysadminWithToken())

    assert "No datasets, contact points, or other publishers" in app.get(
        f"/en/actors/{actor}/delete", headers=headers).get_data(as_text=True)
    assert "No datasets currently reference this contact point." in app.get(
        f"/en/contactpoints/{contact}/delete", headers=headers).get_data(as_text=True)


def test_delete_confirmations_do_not_use_the_search_index(app, org, monkeypatch):
    # The old implementation sent every linked id to Solr in one filter
    # (breaks past ~1024 ids and trusts a possibly stale index). Fail loudly
    # if either page ever calls package_search again.
    actor = _actor()
    contact = _contact(actor)
    _dataset(org, "En", publisher_actor_id=actor, contact_point_ids=[contact])
    headers = _headers(factories.SysadminWithToken())

    def forbid(*args, **kwargs):
        raise AssertionError("package_search must not be used")

    from ckan.plugins import toolkit
    original = toolkit.get_action

    def guarded(name):
        return forbid if name == "package_search" else original(name)

    monkeypatch.setattr(toolkit, "get_action", guarded)

    assert app.get(f"/actors/{actor}/delete", headers=headers).status_code == 200
    assert app.get(f"/contactpoints/{contact}/delete", headers=headers).status_code == 200


def test_english_pages_say_publisher_not_actor(app, org):
    # English UI text also uses "publisher" throughout (URLs and code
    # identifiers keep "actor"; only visible text is checked).
    import re

    actor = _actor()
    contact = _contact(actor)
    _dataset(org, "En", publisher_actor_id=actor)
    headers = _headers(factories.SysadminWithToken())

    for path in (f"/en/actors/{actor}", f"/en/actors/{actor}/datasets", f"/en/actors/{actor}/edit",
                 f"/en/actors/{actor}/delete", "/en/actors", "/en/actors/new",
                 f"/en/contactpoints/{contact}", f"/en/contactpoints/{contact}/delete"):
        soup = BeautifulSoup(app.get(path, headers=headers).get_data(as_text=True), "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = re.sub(r"https?://\S+", "", soup.body.get_text(" ", strip=True))  # URIs are identifiers, not UI text
        assert not re.search(r"\bactors?\b", text, re.I), (path, re.findall(r".{20}\bactors?\b.{20}", text, re.I)[:3])


# --- "Datasets without a publisher link" on /actors ------------------------------------


def test_actors_index_lists_unlinked_datasets_from_the_database(app, org):
    actor = _actor()
    _dataset(org, "Har utgivare", publisher_actor_id=actor)
    for n in range(12):
        _dataset(org, f"Saknar {n:02d}")
    headers = _headers(factories.SysadminWithToken())

    html = app.get("/en/actors", headers=headers).get_data(as_text=True)

    assert "Datasets missing both a publisher and a contact point (12)" in html
    listed = [t for t in _links(html) if t.startswith("Saknar")]
    assert len(listed) == 10 and listed[0] == "Saknar 00"
    assert "Har utgivare" not in html
    assert "Show all 12" in html and "/actors/unlinked-datasets" in html


def test_unlinked_datasets_page_paginates_and_requires_login(app, org):
    for n in range(25):
        _dataset(org, f"Saknar {n:02d}")
    headers = _headers(factories.SysadminWithToken())

    assert app.get("/actors/unlinked-datasets").status_code == 403
    first = app.get("/actors/unlinked-datasets", headers=headers).get_data(as_text=True)
    second = app.get("/actors/unlinked-datasets?page=2", headers=headers).get_data(as_text=True)

    assert len([t for t in _links(first) if t.startswith("Saknar")]) == 20
    assert [t for t in _links(second) if t.startswith("Saknar")] == [f"Saknar {n:02d}" for n in range(20, 25)]
    assert app.get("/actors/unlinked-datasets?page=99", headers=headers).status_code == 404


def test_a_dataset_with_only_a_contact_point_or_only_a_publisher_is_not_unlinked(app, org):
    actor, contact = _actor(), _contact()
    _dataset(org, "Bara utgivare", publisher_actor_id=actor)
    _dataset(org, "Bara kontakt", contact_point_ids=[contact])
    _dataset(org, "Ingenting")
    headers = _headers(factories.SysadminWithToken())

    page = app.get("/actors/unlinked-datasets", headers=headers).get_data(as_text=True)

    assert _links(page) == ["Ingenting"]


def test_unlinked_list_hides_private_datasets_from_non_members(app, org):
    _dataset(org, "Publik olänkad")
    _dataset(org, "Hemlig olänkad", private=True)
    outsider = factories.UserWithToken()

    html = app.get("/actors/unlinked-datasets", headers=_headers(outsider)).get_data(as_text=True)

    assert "Publik olänkad" in html and "Hemlig olänkad" not in html


def test_actors_index_does_not_use_the_search_index(app, org, monkeypatch):
    _dataset(org, "Olänkad")
    headers = _headers(factories.SysadminWithToken())
    from ckan.plugins import toolkit

    original = toolkit.get_action

    def guarded(name):
        if name == "package_search":
            raise AssertionError("package_search must not be used")
        return original(name)

    monkeypatch.setattr(toolkit, "get_action", guarded)

    assert app.get("/actors", headers=headers).status_code == 200
    assert app.get("/actors/unlinked-datasets", headers=headers).status_code == 200
