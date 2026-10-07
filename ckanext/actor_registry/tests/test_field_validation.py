import uuid

import pytest
from bs4 import BeautifulSoup

from ckan import model as ckan_model
from ckan.plugins import toolkit
from ckan.tests import factories, helpers

from ckanext.actor_registry import model, validation

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry scheming_datasets"),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas", "ckanext.actor_registry.tests.fixtures:dcat_test_schema.yaml"
    ),
    pytest.mark.ckan_config(
        "scheming.presets", "ckanext.scheming:presets.json ckanext.dcat.schemas:presets.yaml"
    ),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db"),
]


def _headers(user):
    return {"Authorization": user["token"]}


# --- Pure rules ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [("  Kontakt@Skelleftea.SE ", "kontakt@skelleftea.se"), ("", "")],
)
def test_email_is_trimmed_and_lowercased(raw, expected):
    assert validation.normalise_email(raw) == (expected, None)


@pytest.mark.parametrize("bad", ["not-an-email", "a@b", "a b@example.org", "@example.org", "a@@example.org"])
def test_invalid_email_is_rejected(bad):
    assert validation.normalise_email(bad)[1]


@pytest.mark.parametrize("good", ["https://www.skelleftea.se", "http://example.org/x?y=1", ""])
def test_absolute_http_urls_are_accepted(good):
    assert validation.normalise_url(good)[1] is None


@pytest.mark.parametrize("bad", ["www.skelleftea.se", "ftp://example.org", "javascript:alert(1)", "https://", "https://a b.se"])
def test_non_http_or_relative_urls_are_rejected(bad):
    assert validation.normalise_url(bad)[1]


@pytest.mark.parametrize("good", ["+46 910 73 50 00", "0910-73 50 00", "(0910) 735000", "  +46910735000  ", ""])
def test_reasonable_phone_formats_are_accepted(good):
    assert validation.normalise_phone(good)[1] is None


def test_phone_whitespace_is_collapsed_but_format_is_kept():
    assert validation.normalise_phone("+46   910  73 50 00")[0] == "+46 910 73 50 00"


@pytest.mark.parametrize("bad", ["call me", "12", "+46abc12345"])
def test_implausible_phone_is_rejected(bad):
    assert validation.normalise_phone(bad)[1]


def test_kind_is_limited_to_known_values():
    assert validation.check_kind("person")[1] is None
    assert validation.check_kind("organization")[1] is None
    assert validation.check_kind("robot")[1]


# --- Through the views -----------------------------------------------------------


def test_actor_quick_create_rejects_bad_fields_and_normalises_email(app):
    headers = _headers(factories.SysadminWithToken())

    for data in ({"email": "nope"}, {"url": "www.example.org"}, {"actor_kind": "robot"}):
        response = app.post("/actors/quick-create", data=dict({"name": "X"}, **data), headers=headers)
        assert response.status_code == 409, data
        assert response.json["success"] is False

    ok = app.post(
        "/actors/quick-create",
        data={"name": "Bra", "email": " Info@Example.ORG ", "url": "https://example.org"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert ok.json["actor"]["email"] == "info@example.org"


def test_contactpoint_quick_create_validates_email_phone_and_url(app):
    headers = _headers(factories.SysadminWithToken())

    for data in ({"email": "nope"}, {"phone": "call me"}, {"url": "ftp://x.org"}):
        response = app.post("/contactpoints/quick-create", data=dict({"name": "K"}, **data), headers=headers)
        assert response.status_code == 409, data

    ok = app.post(
        "/contactpoints/quick-create",
        data={"name": "K", "email": "K@Example.org", "phone": "+46   910 73 50 00"},
        headers=headers,
    )
    assert ok.status_code == 200
    assert ok.json["contact_point"]["email"] == "k@example.org"
    assert ok.json["contact_point"]["phone"] == "+46 910 73 50 00"


def test_contactpoint_full_form_shows_field_error_and_does_not_save(app):
    headers = _headers(factories.SysadminWithToken())
    form = app.get("/contactpoints/new", headers=headers)
    token = BeautifulSoup(form.data, "html.parser").select_one('input[name="_csrf_token"]')["value"]

    response = app.post(
        "/contactpoints/new",
        data={"_csrf_token": token, "name": "Felaktig", "email": "nope", "active": "on"},
        headers=headers,
    )

    assert response.status_code == 200
    assert "valid email address" in response.get_data(as_text=True)
    assert all(c.name != "Felaktig" for c in model.all_contact_points(True))


# --- Dataset references (validators) ---------------------------------------------


def _record(cls, name, active=True, **extra):
    record_id = str(uuid.uuid4())
    ckan_model.Session.add(
        cls(id=record_id, name=name, uri=f"https://example.org/{record_id}", active=active, **extra)
    )
    ckan_model.Session.flush()
    return record_id


def _create_dataset(publisher, contacts):
    sysadmin = factories.Sysadmin()
    context = {"user": sysadmin["name"]}
    org = helpers.call_action("organization_create", context=context, name=f"v-{uuid.uuid4().hex}", title="Org")
    return helpers.call_action(
        "package_create",
        context=context,
        name=f"v-{uuid.uuid4().hex}",
        title="Referenstest",
        notes="Text",
        owner_org=org["id"],
        publisher_actor_id=publisher,
        contact_point_ids=contacts,
    )


def test_dataset_accepts_existing_active_references():
    actor = _record(model.Actor, "Aktiv", actor_kind="organization")
    contact = _record(model.ContactPoint, "Kontakt")

    dataset = _create_dataset(actor, [contact])

    assert dataset["publisher_actor_id"] == actor


@pytest.mark.parametrize("kind", ["unknown", "inactive"])
def test_dataset_rejects_missing_or_inactive_publisher(kind):
    ref = str(uuid.uuid4()) if kind == "unknown" else _record(model.Actor, "Av", active=False, actor_kind="organization")

    with pytest.raises(toolkit.ValidationError) as caught:
        _create_dataset(ref, [])

    assert "publisher_actor_id" in caught.value.error_dict


@pytest.mark.parametrize("kind", ["unknown", "inactive"])
def test_dataset_rejects_missing_or_inactive_contact_point(kind):
    actor = _record(model.Actor, "Aktiv", actor_kind="organization")
    ref = str(uuid.uuid4()) if kind == "unknown" else _record(model.ContactPoint, "Av", active=False)

    with pytest.raises(toolkit.ValidationError) as caught:
        _create_dataset(actor, [ref])

    assert "contact_point_ids" in caught.value.error_dict


def test_required_publisher_cannot_be_saved_empty():
    with pytest.raises(toolkit.ValidationError) as caught:
        _create_dataset("", [])

    assert "publisher_actor_id" in caught.value.error_dict


def _page_without_publisher(app, contacts):
    # An older dataset saved before the publisher became required: the form can
    # no longer produce one, so remove the stored link directly.
    dataset = _create_dataset(_record(model.Actor, "Aktiv", actor_kind="organization"), contacts)
    package = ckan_model.Package.get(dataset["id"])
    package.extras = {key: value for key, value in package.extras.items() if key != "publisher_actor_id"}
    ckan_model.Session.commit()
    # package_show reads the search index copy, so refresh it.
    from ckan.lib.search import rebuild
    rebuild(dataset["id"])
    sysadmin = factories.SysadminWithToken()
    html = app.get(f"/dataset/{dataset['name']}",
                   headers={"Authorization": sysadmin["token"]}).get_data(as_text=True)
    prompt = html.split("data-dataset-actor-link-prompt", 1)
    return prompt[1].split("</form>", 1)[0] if len(prompt) == 2 else ""


def test_a_required_publisher_that_is_missing_is_asked_for(app):
    prompt = _page_without_publisher(app, [_record(model.ContactPoint, "Kontakt")])
    assert "Publisher missing." in prompt
    assert 'name="publisher_actor_id"' in prompt
    assert 'name="contact_point_ids"' not in prompt


def test_both_missing_are_named_in_the_heading(app):
    prompt = _page_without_publisher(app, [])
    assert "Publisher and contact point missing." in prompt
    assert 'name="publisher_actor_id"' in prompt and 'name="contact_point_ids"' in prompt


def test_a_required_publisher_has_no_empty_publisher_help(app):
    sysadmin = factories.SysadminWithToken()
    html = app.get("/dataset/new", headers={"Authorization": sysadmin["token"]}).get_data(as_text=True)
    assert "data-publisher-empty-help" not in html
