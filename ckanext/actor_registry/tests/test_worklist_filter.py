"""The /actors worklist of datasets that lack something can show datasets missing
both a publisher and a contact point (the default), only a publisher, only a contact
point, or either one."""

import uuid

import pytest
from bs4 import BeautifulSoup

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


def _headers():
    return {"Authorization": factories.SysadminWithToken()["token"]}


def _links(html):
    return sorted(a.get_text(strip=True) for a in BeautifulSoup(html, "html.parser").select("ul.dataset-list li a"))


@pytest.fixture
def org():
    return helpers.call_action(
        "organization_create", context={"user": factories.Sysadmin()["name"]},
        name=f"o-{uuid.uuid4().hex}", title="Org",
    )


def _dataset(org, title, private=False, **fields):
    return helpers.call_action(
        "package_create", context={"user": factories.Sysadmin()["name"]},
        name=f"d-{uuid.uuid4().hex}", title=title, owner_org=org["id"], private=private, **fields,
    )


@pytest.fixture
def four_datasets(org):
    """One dataset for each combination of having / lacking the two links."""
    actor_id, contact_id = str(uuid.uuid4()), str(uuid.uuid4())
    ckan_model.Session.add_all([
        model.Actor(id=actor_id, name="Utgivare", actor_kind="organization",
                    uri=f"https://example.org/{actor_id}", active=True),
        model.ContactPoint(id=contact_id, name="Kontakt", uri=f"https://example.org/{contact_id}", active=True),
    ])
    ckan_model.Session.commit()
    _dataset(org, "A saknar utgivare", contact_point_ids=[contact_id])
    _dataset(org, "B saknar kontaktpunkt", publisher_actor_id=actor_id)
    _dataset(org, "C saknar båda")
    _dataset(org, "D har båda", publisher_actor_id=actor_id, contact_point_ids=[contact_id])


@pytest.mark.parametrize(
    "missing, expected",
    [
        (None, ["C saknar båda"]),  # the default is unchanged: missing BOTH
        ("both", ["C saknar båda"]),
        ("publisher", ["A saknar utgivare", "C saknar båda"]),
        ("contact_point", ["B saknar kontaktpunkt", "C saknar båda"]),
        ("either", ["A saknar utgivare", "B saknar kontaktpunkt", "C saknar båda"]),
    ],
)
def test_each_filter_lists_the_right_datasets(app, four_datasets, missing, expected):
    query = f"?missing={missing}" if missing else ""

    index = app.get(f"/en/actors{query}", headers=_headers()).get_data(as_text=True)
    full = app.get(f"/en/actors/unlinked-datasets{query}", headers=_headers()).get_data(as_text=True)

    assert _links(index) == expected
    assert _links(full) == expected
    assert "D har båda" not in index and "D har båda" not in full


def test_the_heading_and_the_active_button_follow_the_choice(app, four_datasets):
    page = app.get("/en/actors?missing=either", headers=_headers()).get_data(as_text=True)
    soup = BeautifulSoup(page, "html.parser")

    assert "Datasets missing a publisher or a contact point (3)" in page
    assert soup.select_one("h2#worklist").get_text(strip=True).endswith("(3)")
    active = soup.select("ul.nav-pills a.nav-link.active")
    assert [a.get_text(strip=True) for a in active] == ["Either"]
    # all four choices are offered as links that keep the choice
    hrefs = [a["href"] for a in soup.select("ul.nav-pills a.nav-link")]
    assert any("missing=publisher" in h for h in hrefs) and any("missing=contact_point" in h for h in hrefs)


def test_the_filter_is_translated(app, four_datasets):
    page = app.get("/sv/actors?missing=publisher", headers=_headers()).get_data(as_text=True)

    assert "Datamängder utan utgivare (2)" in page
    assert "Saknar:" in page


def test_an_unknown_filter_is_a_404(app, four_datasets):
    assert app.get("/actors?missing=bogus", headers=_headers(), expect_errors=True).status_code == 404
    assert app.get("/actors/unlinked-datasets?missing=bogus", headers=_headers(), expect_errors=True).status_code == 404


def test_pagination_keeps_the_choice(app, org):
    for n in range(25):
        _dataset(org, f"Saknar {n:02d}")

    first = app.get("/en/actors/unlinked-datasets?missing=publisher", headers=_headers()).get_data(as_text=True)
    second = app.get("/en/actors/unlinked-datasets?missing=publisher&page=2", headers=_headers()).get_data(as_text=True)

    assert len(_links(first)) == 20 and len(_links(second)) == 5
    assert "missing=publisher" in first and "page=2" in first  # the pager link carries both
    index = app.get("/en/actors?missing=publisher", headers=_headers()).get_data(as_text=True)
    assert "Show all 25" in index and "missing=publisher" in index


def test_private_datasets_stay_hidden_in_every_mode(app, org):
    _dataset(org, "Publik utan allt")
    _dataset(org, "Hemlig utan allt", private=True)
    outsider = {"Authorization": factories.UserWithToken()["token"]}

    for missing in ("both", "publisher", "contact_point", "either"):
        html = app.get(f"/actors/unlinked-datasets?missing={missing}", headers=outsider).get_data(as_text=True)
        assert "Publik utan allt" in html and "Hemlig utan allt" not in html, missing


def test_the_empty_state_says_so(app, org):
    page = app.get("/en/actors?missing=contact_point", headers=_headers()).get_data(as_text=True)

    assert "No datasets are missing this." in page
    default = app.get("/en/actors", headers=_headers()).get_data(as_text=True)
    assert "All datasets have at least one publisher or contact point linked." in default
