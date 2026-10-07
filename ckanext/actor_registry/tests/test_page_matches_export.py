"""Ground rule: what visitors see on the dataset page is what the DCAT export
contains. Any exception must be a deliberate decision, documented in the
README ("What visitors see is what is exported")."""

import uuid

import pytest

from ckan import model as ckan_model
from ckan.tests import factories, helpers

from ckanext.actor_registry import model

pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "dcat actor_registry scheming_datasets"),
    pytest.mark.ckan_config(
        "scheming.dataset_schemas", "ckanext.actor_registry.examples:actor_registry_schema.yaml"),
    pytest.mark.ckan_config("scheming.presets", "ckanext.scheming:presets.json"),
    pytest.mark.ckan_config("ckanext.dcat.rdf.profiles", "actor_registry_euro_dcat_ap_3"),
    pytest.mark.usefixtures("with_plugins", "clean_db", "actor_registry_db"),
]


def _save(record):
    ckan_model.Session.add(record)
    ckan_model.Session.commit()
    return record


def _actor(name, **fields):
    return _save(model.Actor(id=str(uuid.uuid4()), name=name, actor_kind="organization",
                             uri=f"https://example.org/a/{uuid.uuid4()}", active=True, **fields))


def _contact(name):
    return _save(model.ContactPoint(id=str(uuid.uuid4()), name=name, email=f"{uuid.uuid4().hex[:8]}@example.org",
                                    uri=f"https://example.org/cp/{uuid.uuid4()}", active=True))


def _change(record_type, record_id, **fields):
    ckan_model.Session.expire_all()
    record = ckan_model.Session.get(record_type, record_id)
    for key, value in fields.items():
        setattr(record, key, value)
    ckan_model.Session.commit()


def _page_and_export(app, **fields):
    sysadmin = factories.Sysadmin()
    org = factories.Organization(title="City of Riverton")
    dataset = helpers.call_action("package_create", context={"user": sysadmin["name"]},
                                  name=f"d-{uuid.uuid4().hex[:10]}", title="Bathing sites",
                                  notes="Water samples.", owner_org=org["id"], **fields)
    return dataset, lambda: (
        app.get(f"/dataset/{dataset['name']}").get_data(as_text=True),
        helpers.call_action("dcat_dataset_show", context={"user": sysadmin["name"]},
                            id=dataset["id"], format="ttl"),
    )


def _on_both(read, name):
    page, export = read()
    return (name in page, name in export)


def test_an_inactive_contact_point_is_shown_and_exported(app):
    contact = _contact("Old Desk")
    _, read = _page_and_export(app, contact_point_ids=[contact.id])
    _change(model.ContactPoint, contact.id, active=False)
    assert _on_both(read, "Old Desk") == (True, True)


def test_an_inactive_publisher_is_shown_and_exported(app):
    actor = _actor("Old Board")
    _, read = _page_and_export(app, publisher_actor_id=actor.id)
    _change(model.Actor, actor.id, active=False)
    assert _on_both(read, "Old Board") == (True, True)


def test_a_merged_publisher_is_replaced_by_its_target_on_both(app):
    target, merged = _actor("New Board"), _actor("Old Board")
    _, read = _page_and_export(app, publisher_actor_id=merged.id)
    _change(model.Actor, merged.id, active=False, merged_into_id=target.id)
    assert _on_both(read, "New Board") == (True, True)
    assert _on_both(read, "Old Board") == (False, False)


def test_missing_references_are_on_neither(app):
    dataset, read = _page_and_export(app)
    package = ckan_model.Package.get(dataset["id"])
    package.extras = dict(package.extras, publisher_actor_id="gone-actor", contact_point_ids='["gone-contact"]')
    ckan_model.Session.commit()
    from ckan.lib.search import rebuild
    rebuild(dataset["id"])
    page, export = read()
    for missing in ("gone-actor", "gone-contact"):
        assert missing not in page and missing not in export


def test_active_records_are_on_both(app):
    _, read = _page_and_export(app, publisher_actor_id=_actor("City Board").id,
                               contact_point_ids=[_contact("Open Data Desk").id])
    assert _on_both(read, "City Board") == (True, True)
    assert _on_both(read, "Open Data Desk") == (True, True)


def test_old_fields_the_schema_does_not_show_are_not_exported(app):
    # The example schema has no Author field, so the page never shows it.
    _, read = _page_and_export(app, author="Ann Author", author_email="ann@example.org",
                               contact_point_ids=[])
    page, export = read()
    assert "Ann Author" not in page
    assert "Ann Author" not in export and "ann@example.org" not in export
