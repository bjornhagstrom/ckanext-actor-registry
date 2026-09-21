"""End-to-end flows from the CKAN 2.12 delivery-test checklist (block 5 and
the remaining tests): clean install, dataset form, clearing an optional
publisher, permissions, edge cases and persistence."""

import uuid

import pytest
from sqlalchemy import inspect, text

from ckan import model as ckan_model
from ckan.plugins import toolkit
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


def _record(cls, name, **extra):
    record_id = str(uuid.uuid4())
    ckan_model.Session.add(cls(id=record_id, name=name, uri=f"https://example.org/{record_id}", **extra))
    ckan_model.Session.commit()
    return record_id


def _actor(name="Skellefteå kommun", **extra):
    return _record(model.Actor, name, actor_kind="organization", active=extra.pop("active", True), **extra)


def _contact(name="Kontaktcenter", **extra):
    return _record(model.ContactPoint, name, active=extra.pop("active", True), **extra)


def _dataset(**fields):
    sysadmin = factories.Sysadmin()
    context = {"user": sysadmin["name"]}
    org = helpers.call_action("organization_create", context=context, name=f"f-{uuid.uuid4().hex}", title="Org")
    return helpers.call_action(
        "package_create", context=context, name=f"f-{uuid.uuid4().hex}", title="Flödestest",
        owner_org=org["id"], **fields,
    ), context


# --- Clean install / migration from an empty database ------------------------------


def test_clean_install_migrates_from_empty_database_to_head():
    # actor_registry_db already ran the migrations against a freshly
    # cleaned database; assert the whole schema is there, incl. the index.
    inspector = inspect(ckan_model.meta.engine)
    tables = set(inspector.get_table_names())
    assert {
        "actor_registry_actor", "contactpoints_contact_point",
        "actor_registry_user_preference", "actor_registry_recent_contact_point",
    } <= tables
    indexes = {i["name"] for i in inspector.get_indexes("actor_registry_actor")}
    assert "actor_registry_actor_identifier_uq" in indexes
    head = ckan_model.Session.execute(text("SELECT version_num FROM alembic_version_actor_registry")).scalar() \
        if "alembic_version_actor_registry" in tables else None
    assert head in (None, "actor_registry_006")


# --- /dataset/new ---------------------------------------------------------------------


def test_dataset_new_form_has_publisher_and_contact_point_fields(app):
    actor_id, contact_id = _actor(), _contact()
    user = factories.SysadminWithToken()

    response = app.get("/dataset/new", headers=_headers(user))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="publisher_actor_id"' in html and 'name="contact_point_ids"' in html
    assert f'value="{actor_id}"' in html and f'value="{contact_id}"' in html
    # Shared inline-dialog help text is rendered with the fields.
    assert "A unique value for this organization or person" in html
    # Contact point dialog offers the owning organization, and options carry it.
    assert 'data-field="actor_id"' in html and "data-actor-id" in html


# --- Clearing an optional publisher ----------------------------------------------------


def test_empty_choice_clears_a_previously_saved_optional_publisher():
    actor_id = _actor()
    dataset, context = _dataset(publisher_actor_id=actor_id)
    assert dataset["publisher_actor_id"] == actor_id

    helpers.call_action("package_patch", context=context, id=dataset["id"], publisher_actor_id="")

    cleared = helpers.call_action("package_show", context=context, id=dataset["id"])
    assert not cleared.get("publisher_actor_id")


# --- Permissions -------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/actors", "/actors/new", "/contactpoints", "/contactpoints/new"])
def test_anonymous_visitors_cannot_use_registry_pages(app, path):
    assert app.get(path).status_code == 403


def test_anonymous_visitors_cannot_post_quick_create(app):
    assert app.post("/actors/quick-create", data={"name": "X"}).status_code in (403, 401)
    assert app.post("/contactpoints/quick-create", data={"name": "X"}).status_code in (403, 401)


def test_normal_user_can_edit_but_not_delete_or_merge(app):
    actor_id, contact_id = _actor(), _contact()
    user = factories.UserWithToken()
    headers = _headers(user)

    assert app.get("/actors/new", headers=headers).status_code == 200
    assert app.get(f"/actors/{actor_id}/edit", headers=headers).status_code == 200
    assert app.get(f"/actors/{actor_id}/delete", headers=headers).status_code == 403
    assert app.get(f"/contactpoints/{contact_id}/delete", headers=headers).status_code == 403
    assert app.get("/actors/merge", headers=headers).status_code in (403, 404)


def test_sysadmin_can_open_delete_confirmations(app):
    actor_id, contact_id = _actor(), _contact()
    headers = _headers(factories.SysadminWithToken())

    assert app.get(f"/actors/{actor_id}/delete", headers=headers).status_code == 200
    assert app.get(f"/contactpoints/{contact_id}/delete", headers=headers).status_code == 200


def test_public_registry_record_pages_are_readable_without_login(app):
    actor_id, contact_id = _actor(), _contact()

    assert app.get(f"/actors/{actor_id}").status_code == 200
    assert app.get(f"/contactpoints/{contact_id}").status_code == 200


# --- Edge cases ---------------------------------------------------------------------------


def test_blank_name_is_rejected_in_quick_create(app):
    headers = _headers(factories.SysadminWithToken())

    assert app.post("/actors/quick-create", data={"name": "   "}, headers=headers).status_code == 400
    assert app.post("/contactpoints/quick-create", data={"name": ""}, headers=headers).status_code == 400


def test_dataset_can_reference_several_contact_points():
    actor_id = _actor()
    contacts = [_contact(f"Kontakt {i}") for i in range(3)]

    dataset, _ = _dataset(publisher_actor_id=actor_id, contact_point_ids=contacts)

    assert sorted(dataset["contact_point_ids"]) == sorted(contacts)


# --- Persistence ---------------------------------------------------------------------------


def test_records_and_dataset_links_survive_a_dropped_session():
    actor_id, contact_id = _actor(), _contact()
    dataset, context = _dataset(publisher_actor_id=actor_id, contact_point_ids=[contact_id])

    # Stand-in for a restart: drop every cached ORM object and connection
    # state, so everything below is re-read from the database.
    ckan_model.Session.remove()
    ckan_model.meta.engine.dispose()

    assert model.get_actor(actor_id).name == "Skellefteå kommun"
    assert model.get_contact_point(contact_id).name == "Kontaktcenter"
    shown = helpers.call_action("package_show", context=context, id=dataset["id"])
    assert shown["publisher_actor_id"] == actor_id
    assert list(shown["contact_point_ids"]) == [contact_id]
    assert dataset["id"] in model.datasets_for_actor(actor_id)["publisher"]
