from datetime import datetime

import pytest
from sqlalchemy import inspect, text

from ckan import model as ckan_model
from ckan.cli.db import _run_migrations, current_revision


pytestmark = [
    pytest.mark.integration,
    pytest.mark.ckan_config("ckan.plugins", "actor_registry"),
    pytest.mark.usefixtures("with_plugins", "actor_registry_db"),
]


def _table_names():
    return set(inspect(ckan_model.meta.engine).get_table_names())


def test_upgrade_from_contactpoints_prototype_preserves_existing_contact():
    """Rehearse the exact upgrade path from the unpublished prototype."""
    _run_migrations("actor_registry", "contactpoints_001", forward=False)
    assert current_revision("actor_registry") == "contactpoints_001"
    assert "contactpoints_contact_point" in _table_names()
    assert "actor_registry_actor" not in _table_names()

    created = datetime(2026, 1, 15, 12, 0, 0)
    ckan_model.Session.execute(
        text(
            """
            INSERT INTO contactpoints_contact_point
                (id, name, email, phone, url, uri, active, created, modified)
            VALUES
                (:id, :name, :email, :phone, :url, :uri, :active, :created, :modified)
            """
        ),
        {
            "id": "legacy-contact",
            "name": "Befintlig kontaktpunkt",
            "email": "kontakt@example.org",
            "phone": "+46 910 12 34 56",
            "url": "https://example.org/contact",
            "uri": "https://example.org/contact-points/legacy",
            "active": True,
            "created": created,
            "modified": created,
        },
    )
    ckan_model.Session.commit()

    _run_migrations("actor_registry", "head", forward=True)
    assert current_revision("actor_registry") == "actor_registry_005 (head)"

    tables = _table_names()
    assert {
        "actor_registry_actor",
        "actor_registry_user_preference",
        "actor_registry_recent_contact_point",
    }.issubset(tables)
    contact_columns = {
        column["name"]
        for column in inspect(ckan_model.meta.engine).get_columns(
            "contactpoints_contact_point"
        )
    }
    assert "actor_id" in contact_columns
    saved = ckan_model.Session.execute(
        text(
            """
            SELECT name, email, phone, uri, actor_id
            FROM contactpoints_contact_point
            WHERE id = :id
            """
        ),
        {"id": "legacy-contact"},
    ).mappings().one()
    assert dict(saved) == {
        "name": "Befintlig kontaktpunkt",
        "email": "kontakt@example.org",
        "phone": "+46 910 12 34 56",
        "uri": "https://example.org/contact-points/legacy",
        "actor_id": None,
    }

    # Running the current migration again must be harmless during restarts.
    _run_migrations("actor_registry", "head", forward=True)
    assert current_revision("actor_registry") == "actor_registry_005 (head)"
