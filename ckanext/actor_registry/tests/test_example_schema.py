"""The shipped example schema must load and work, so the docs can point at it."""

import uuid

import pytest

from ckan.plugins import toolkit
from ckan.tests import factories, helpers

from ckanext.actor_registry import model  # noqa: F401  (registers the models)
from ckan import model as ckan_model

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry scheming_datasets"),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas", "ckanext.actor_registry.examples:actor_registry_schema.yaml"
    ),
    pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db"),
]


def _create(**fields):
    sysadmin = factories.Sysadmin()
    context = {"user": sysadmin["name"]}
    org = helpers.call_action("organization_create", context=context, name=f"e-{uuid.uuid4().hex}", title="Org")
    return helpers.call_action(
        "package_create", context=context, name=f"e-{uuid.uuid4().hex}", title="Exempel", notes="Beskrivning",
        owner_org=org["id"], **fields,
    )


def test_example_schema_accepts_registered_publisher_and_contact_point():
    actor_id, contact_id = str(uuid.uuid4()), str(uuid.uuid4())
    ckan_model.Session.add_all([
        model.Actor(id=actor_id, name="Utgivare", actor_kind="organization", uri=f"https://example.org/{actor_id}", active=True),
        model.ContactPoint(id=contact_id, name="Kontakt", uri=f"https://example.org/{contact_id}", active=True),
    ])
    ckan_model.Session.commit()

    dataset = _create(publisher_actor_id=actor_id, contact_point_ids=[contact_id])

    assert dataset["publisher_actor_id"] == actor_id


def _actor(active=True):
    actor_id = str(uuid.uuid4())
    ckan_model.Session.add(model.Actor(id=actor_id, name="City of Riverton", actor_kind="organization",
                                       uri=f"https://example.org/{actor_id}", active=active))
    ckan_model.Session.commit()
    return actor_id


def _contact():
    contact_id = str(uuid.uuid4())
    ckan_model.Session.add(model.ContactPoint(id=contact_id, name="Open Data Desk",
                                              uri=f"https://example.org/{contact_id}", active=True))
    ckan_model.Session.commit()
    return contact_id


def _page(app, dataset):
    sysadmin = factories.SysadminWithToken()
    return app.get(f"/dataset/{dataset['name']}",
                   headers={"Authorization": sysadmin["token"]}).get_data(as_text=True)


@pytest.mark.parametrize("fields", [{}, {"publisher_actor_id": ""}, {"publisher_actor_id": None}])
def test_example_schema_publisher_is_optional(fields):
    dataset = _create(**fields)
    assert not dataset.get("publisher_actor_id")


@pytest.mark.parametrize("bad", ["no-such-publisher", "inactive"])
def test_example_schema_rejects_an_unknown_or_inactive_publisher(bad):
    value = _actor(active=False) if bad == "inactive" else bad
    with pytest.raises(toolkit.ValidationError) as caught:
        _create(publisher_actor_id=value)
    assert "publisher_actor_id" in caught.value.error_dict


def test_example_schema_an_empty_choice_clears_the_publisher():
    dataset = _create(publisher_actor_id=_actor())
    sysadmin = factories.Sysadmin()
    patched = helpers.call_action("package_patch", context={"user": sysadmin["name"]},
                                  id=dataset["id"], publisher_actor_id="")
    assert not patched.get("publisher_actor_id")


def test_the_form_explains_an_empty_optional_publisher(app):
    sysadmin = factories.SysadminWithToken()
    html = app.get("/dataset/new", headers={"Authorization": sysadmin["token"]}).get_data(as_text=True)
    assert "data-publisher-empty-help" in html
    assert "the organization is given as publisher" in html


def test_no_prompt_and_no_publisher_shown_when_only_the_optional_publisher_is_empty(app):
    html = _page(app, _create(contact_point_ids=[_contact()]))
    assert "data-dataset-actor-link-prompt" not in html
    assert 'class="publisher"' not in html


def test_the_prompt_asks_only_for_the_contact_point_when_the_publisher_is_optional(app):
    html = _page(app, _create())
    assert "data-dataset-actor-link-prompt" in html
    assert "Contact point missing." in html
    assert 'name="publisher_actor_id"' not in html.split("data-dataset-actor-link-prompt", 1)[1].split("</form>", 1)[0]


def test_example_schema_labels_cover_en_sv_and_sv_SE():
    schema = toolkit.get_action("scheming_dataset_schema_show")({}, {"type": "dataset"})
    for field in schema["dataset_fields"]:
        assert {"en", "sv", "sv_SE"} <= set(field["label"]), field["field_name"]
