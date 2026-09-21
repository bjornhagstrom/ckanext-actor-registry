import uuid

import pytest
from bs4 import BeautifulSoup
from sqlalchemy.exc import IntegrityError

from ckan import model as ckan_model
from ckan.plugins import toolkit
from ckan.tests import factories

from ckanext.actor_registry import model

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry"),
    pytest.mark.usefixtures("with_plugins", "actor_registry_db"),
]

SCHEME = "SE:ORGNR"
IDENTIFIER = "212000-2643"


def _headers(user_with_token):
    return {"Authorization": user_with_token["token"]}


def _csrf_token(response):
    field = BeautifulSoup(response.data, "html.parser").select_one('input[name="_csrf_token"]')
    assert field is not None
    return field["value"]


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
    ckan_model.Session.commit()
    return item


def _quick_create(app, headers, **data):
    return app.post("/actors/quick-create", data=dict({"name": "Ny utgivare"}, **data), headers=headers)


# --- Model / database constraint ----------------------------------------


def test_database_rejects_duplicate_active_identifier_pair():
    _actor("Första", identifier=IDENTIFIER, identifier_scheme=SCHEME)
    with pytest.raises(IntegrityError):
        _actor("Andra", identifier=IDENTIFIER, identifier_scheme=SCHEME)
    ckan_model.Session.rollback()


def test_database_allows_same_identifier_in_other_scheme_retired_and_blank():
    _actor("Första", identifier=IDENTIFIER, identifier_scheme=SCHEME)
    _actor("Annat system", identifier=IDENTIFIER, identifier_scheme="ORCID")
    _actor("Pensionerad", identifier=IDENTIFIER, identifier_scheme=SCHEME, active=False)
    _actor("Tom 1", identifier="", identifier_scheme="")
    _actor("Tom 2", identifier="", identifier_scheme="")


# --- Quick-create dialog ---------------------------------------------------


def test_quick_create_duplicate_names_existing_actor_in_localised_error(app):
    _actor("Skellefteå kommun", identifier=IDENTIFIER, identifier_scheme=SCHEME)
    headers = _headers(factories.SysadminWithToken())

    response = _quick_create(app, headers, identifier=IDENTIFIER, identifier_scheme=SCHEME)

    assert response.status_code == 409
    assert response.json["success"] is False
    error = response.json["error"]
    assert IDENTIFIER in error and SCHEME in error and "Skellefteå kommun" in error
    assert "Load failed" not in error


def test_quick_create_same_identifier_in_other_scheme_is_allowed(app):
    _actor("Skellefteå kommun", identifier=IDENTIFIER, identifier_scheme=SCHEME)
    headers = _headers(factories.SysadminWithToken())

    response = _quick_create(app, headers, identifier=IDENTIFIER, identifier_scheme="ORCID")

    assert response.status_code == 200


@pytest.mark.parametrize(
    "data", [{"identifier": IDENTIFIER}, {"identifier_scheme": SCHEME}], ids=["only-id", "only-scheme"]
)
def test_quick_create_requires_identifier_and_scheme_together(app, data):
    headers = _headers(factories.SysadminWithToken())

    response = _quick_create(app, headers, **data)

    assert response.status_code == 409
    assert response.json["success"] is False


def test_quick_create_allows_neither_identifier_nor_scheme(app):
    headers = _headers(factories.SysadminWithToken())

    assert _quick_create(app, headers).status_code == 200


def test_quick_create_ignores_retired_actor_with_same_identifier(app):
    _actor("Gammal", identifier=IDENTIFIER, identifier_scheme=SCHEME, active=False)
    headers = _headers(factories.SysadminWithToken())

    assert _quick_create(app, headers, identifier=IDENTIFIER, identifier_scheme=SCHEME).status_code == 200


# --- Quick-edit dialog -----------------------------------------------------


def test_quick_edit_conflict_reports_existing_actor_but_own_pair_is_fine(app):
    _actor("Skellefteå kommun", identifier=IDENTIFIER, identifier_scheme=SCHEME)
    other = _actor("Annan")
    headers = _headers(factories.SysadminWithToken())

    conflict = app.post(
        f"/actors/{other.id}/quick-edit",
        data={"name": "Annan", "identifier": IDENTIFIER, "identifier_scheme": SCHEME},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert "Skellefteå kommun" in conflict.json["error"]

    ok = app.post(
        f"/actors/{other.id}/quick-edit",
        data={"name": "Annan", "identifier": "X-1", "identifier_scheme": SCHEME},
        headers=headers,
    )
    assert ok.status_code == 200
    # Re-saving an actor with its own pair must not conflict with itself.
    again = app.post(
        f"/actors/{other.id}/quick-edit",
        data={"name": "Annan", "identifier": "X-1", "identifier_scheme": SCHEME},
        headers=headers,
    )
    assert again.status_code == 200


# --- Full forms --------------------------------------------------------------


def test_full_form_create_shows_conflict_and_does_not_save(app):
    _actor("Skellefteå kommun", identifier=IDENTIFIER, identifier_scheme=SCHEME)
    headers = _headers(factories.SysadminWithToken())
    form = app.get("/actors/new", headers=headers)

    response = app.post(
        "/actors/new",
        data={
            "_csrf_token": _csrf_token(form),
            "name": "Dubblett",
            "identifier": IDENTIFIER,
            "identifier_scheme": SCHEME,
            "active": "on",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert "Skellefteå kommun" in response.get_data(as_text=True)
    names = [a.name for a in model.all_actors()]
    assert "Dubblett" not in names


def test_full_form_edit_shows_conflict_and_does_not_save(app):
    _actor("Skellefteå kommun", identifier=IDENTIFIER, identifier_scheme=SCHEME)
    other = _actor("Annan")
    headers = _headers(factories.SysadminWithToken())
    form = app.get(f"/actors/{other.id}/edit", headers=headers)

    response = app.post(
        f"/actors/{other.id}/edit",
        data={
            "_csrf_token": _csrf_token(form),
            "name": "Annan",
            "identifier": IDENTIFIER,
            "identifier_scheme": SCHEME,
            "active": "on",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert "Skellefteå kommun" in response.get_data(as_text=True)
    ckan_model.Session.expire_all()
    assert not model.get_actor(other.id).identifier


# --- Merge interaction -------------------------------------------------------


def test_merge_can_adopt_the_retired_actors_identifier():
    keep = _actor("Kvar")
    merge = _actor("Bort", identifier=IDENTIFIER, identifier_scheme=SCHEME)
    sysadmin = factories.Sysadmin()

    toolkit.get_action("actor_registry_actor_merge")(
        {"user": sysadmin["name"]},
        {
            "keep_id": keep.id,
            "merge_id": merge.id,
            "fields": {"identifier": IDENTIFIER, "identifier_scheme": SCHEME},
        },
    )

    ckan_model.Session.expire_all()
    assert model.get_actor(keep.id).identifier == IDENTIFIER
    assert model.get_actor(merge.id).active is False
