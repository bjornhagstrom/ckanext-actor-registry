"""Length limits, URI rules and re-use of CKAN's own email validation.

Before the limits existed, a value longer than its database column was an unhandled
DataError, i.e. an HTTP 500, instead of a message."""

import uuid

import pytest
from bs4 import BeautifulSoup

from ckan import model as ckan_model
from ckan.tests import factories

from ckanext.actor_registry import model, validation

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry"),
    pytest.mark.usefixtures("with_plugins", "actor_registry_db"),
]


def _headers():
    return {"Authorization": factories.SysadminWithToken()["token"]}


def _actor_post(app, **data):
    return app.post("/actors/quick-create", data=dict({"name": "Ok"}, **data), headers=_headers())


def _contact_post(app, **data):
    return app.post("/contactpoints/quick-create", data=dict({"name": "Ok"}, **data), headers=_headers())


# --- Length limits: exactly at the limit is fine, one over is a message, never a 500 ---


@pytest.mark.parametrize(
    "field, limit, extra",
    [
        ("name", 255, {}),
        ("identifier", 255, {"identifier_scheme": "S"}),
        ("identifier_scheme", 255, {"identifier": "1"}),
        ("description", 10000, {}),
    ],
)
def test_actor_fields_stop_at_their_limit(app, field, limit, extra):
    too_long = _actor_post(app, **dict(extra, **{field: "x" * (limit + 1)}))
    assert too_long.status_code == 409
    assert str(limit) in too_long.json["error"]

    at_limit = _actor_post(app, **dict(extra, **{"name": "Ok", field: "x" * limit, "identifier": extra.get("identifier", "") or ("y" if field == "identifier_scheme" else "")}))
    assert at_limit.status_code in (200, 409)  # 409 only for the identifier clash of two identical values
    assert "characters" not in (at_limit.json.get("error") or "")


def test_actor_email_and_urls_have_limits_too(app):
    assert _actor_post(app, email="a" * 320 + "@example.org").status_code == 409
    assert _actor_post(app, url="https://example.org/" + "a" * 2048).status_code == 409
    assert _actor_post(app, uri="https://example.org/" + "a" * 2048).status_code == 409


@pytest.mark.parametrize(
    "data",
    [{"name": "x" * 256}, {"phone": "1" * 101}, {"email": "a" * 320 + "@example.org"},
     {"url": "https://example.org/" + "a" * 2048}],
)
def test_contact_point_fields_stop_at_their_limit(app, data):
    response = _contact_post(app, **data)
    assert response.status_code == 409
    assert "at most" in response.json["error"]


def test_the_full_form_shows_the_length_error_instead_of_failing(app):
    headers = _headers()
    form = app.get("/actors/new", headers=headers)
    token = BeautifulSoup(form.data, "html.parser").select_one('input[name="_csrf_token"]')["value"]

    response = app.post("/actors/new", data={"_csrf_token": token, "name": "x" * 300, "active": "on"}, headers=headers)

    assert response.status_code == 200
    assert "at most 255 characters" in response.get_data(as_text=True)


def test_length_error_is_translated(app):
    response = app.post("/sv/actors/quick-create", data={"name": "x" * 300}, headers=_headers())

    assert response.status_code == 409
    assert "högst 255 tecken" in response.json["error"]


# --- URI and type ---------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "not a uri", "ftp://example.org/x", "data:text/html,x", "https://", "urn:"])
def test_a_bad_uri_or_type_is_rejected(app, bad):
    for field in ("uri", "actor_type"):
        response = _actor_post(app, **{field: bad})
        assert response.status_code == 409, (field, bad)
    assert _contact_post(app, uri=bad).status_code == 409


@pytest.mark.parametrize("good", ["https://example.org/id/1", "http://example.org/a", "urn:uuid:6e8bc430-9c3a-11d9-9669-0800200c9a66"])
def test_absolute_uris_are_accepted(app, good):
    assert _actor_post(app, name="A " + good[-6:], uri=good, actor_type=good).status_code == 200


def test_a_record_saved_before_the_rules_can_still_be_edited(app):
    # Legacy row: a URI (and email) that today's rules would reject. Editing an unrelated
    # field through a dialog that does not even show them must not be blocked by them.
    actor_id = str(uuid.uuid4())
    ckan_model.Session.add(model.Actor(id=actor_id, name="Gammal", actor_kind="organization",
                                       uri="not-a-uri", email="Broken..Mail@@x", active=True))
    ckan_model.Session.commit()

    response = app.post(f"/actors/{actor_id}/quick-edit", data={"name": "Gammal, nytt namn"}, headers=_headers())

    assert response.status_code == 200
    assert response.json["actor"]["name"] == "Gammal, nytt namn"
    assert response.json["actor"]["uri"] == "not-a-uri"  # untouched


def test_but_changing_a_bad_field_to_another_bad_value_is_still_rejected(app):
    actor_id = str(uuid.uuid4())
    ckan_model.Session.add(model.Actor(id=actor_id, name="Gammal2", actor_kind="organization",
                                       uri="not-a-uri", active=True))
    ckan_model.Session.commit()

    response = app.post(f"/actors/{actor_id}/quick-edit",
                        data={"name": "Gammal2", "uri": "javascript:alert(1)"}, headers=_headers())

    assert response.status_code == 409


# --- Email: CKAN's own validator ---------------------------------------------------------


@pytest.mark.parametrize("bad", ["a..b@example.org", ".a@example.org", "a@b", "no-at-sign", "a@@b.se", "a@b..se"])
def test_email_is_checked_by_ckans_own_validator(bad):
    # Rejected by ckan.logic.validators.email_validator (stricter than a plain "x@y.z"
    # pattern about dots), or ("a@b") by the extra rule that the domain needs a dot,
    # since CKAN itself accepts a host with no top-level domain.
    assert validation.normalise_email(bad)[1]


@pytest.mark.parametrize("good", ["info@skelleftea.se", "first.last+tag@example.org", " INFO@Example.ORG "])
def test_ordinary_emails_are_still_accepted_and_lowercased(good):
    value, error = validation.normalise_email(good)
    assert error is None and value == good.strip().lower()
