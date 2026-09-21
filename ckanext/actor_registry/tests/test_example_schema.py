"""The shipped example schema must load and work, so the docs can point at it."""

import uuid

import pytest

from ckan.plugins import toolkit
from ckan.tests import factories, helpers

from ckanext.actor_registry import model  # noqa: F401  (registers the models)
from ckan import model as ckan_model

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "scheming_datasets actor_registry"),
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


def test_example_schema_requires_publisher_with_clear_error():
    with pytest.raises(toolkit.ValidationError) as caught:
        _create(publisher_actor_id="")

    assert "publisher_actor_id" in caught.value.error_dict


def test_example_schema_labels_cover_en_sv_and_sv_SE():
    schema = toolkit.get_action("scheming_dataset_schema_show")({}, {"type": "dataset"})
    for field in schema["dataset_fields"]:
        assert {"en", "sv", "sv_SE"} <= set(field["label"]), field["field_name"]
