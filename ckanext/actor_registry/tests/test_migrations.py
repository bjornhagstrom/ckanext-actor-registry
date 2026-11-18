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
    assert current_revision("actor_registry") == "actor_registry_010 (head)"

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
    assert current_revision("actor_registry") == "actor_registry_010 (head)"


def test_migration_006_fails_clearly_on_pre_existing_duplicate_identifiers():
    """006 adds a uniqueness constraint; a catalogue with existing duplicates must be
    told so clearly (the documented, expected behaviour), not silently corrupted or
    silently left half-migrated.
    """
    _run_migrations("actor_registry", "actor_registry_005", forward=False)
    assert current_revision("actor_registry") == "actor_registry_005"

    created = datetime(2026, 1, 15, 12, 0, 0)
    for suffix in "ab":
        ckan_model.Session.execute(
            text(
                """
                INSERT INTO actor_registry_actor
                    (id, name, actor_kind, identifier, identifier_scheme, uri, active, created, modified)
                VALUES
                    (:id, :name, 'organization', :identifier, :identifier_scheme, :uri, true, :created, :modified)
                """
            ),
            {
                "id": "duplicate-" + suffix,
                "name": "Dubblettaktör " + suffix,
                "identifier": "5566778899",
                "identifier_scheme": "org-nr",
                "uri": "https://example.org/actors/duplicate-" + suffix,
                "created": created,
                "modified": created,
            },
        )
    ckan_model.Session.commit()

    with pytest.raises(Exception, match="(?i)duplicate|actor_registry_actor_identifier_uq"):
        _run_migrations("actor_registry", "head", forward=True)
    ckan_model.Session.rollback()

    # Neither duplicate row was dropped, and the migration did not silently advance.
    assert current_revision("actor_registry") != "actor_registry_010 (head)"
    remaining = ckan_model.Session.execute(
        text("SELECT count(*) FROM actor_registry_actor WHERE identifier = '5566778899'")
    ).scalar()
    assert remaining == 2


def test_migration_007_decision_log_can_be_removed_and_added_again():
    def has_table():
        return ckan_model.Session.execute(
            text("SELECT to_regclass('actor_registry_migration_decision') IS NOT NULL")
        ).scalar()

    assert has_table()
    _run_migrations("actor_registry", "actor_registry_006", forward=False)
    assert current_revision("actor_registry") == "actor_registry_006"
    assert not has_table()
    _run_migrations("actor_registry", "head", forward=True)
    assert current_revision("actor_registry") == "actor_registry_010 (head)"
    assert has_table()


def test_migration_008_decision_values_can_be_removed_and_added_again():
    def columns():
        return {column["name"] for column in inspect(ckan_model.meta.engine).get_columns(
            "actor_registry_migration_decision")}

    assert "source_values" in columns()
    _run_migrations("actor_registry", "actor_registry_007", forward=False)
    assert "source_values" not in columns()
    _run_migrations("actor_registry", "head", forward=True)
    assert "source_values" in columns()


def test_migration_009_drops_the_page_language_from_uris_the_registry_made():
    rows = {
        # (table, id, uri before, uri after)
        "actor_sv": ("actor_registry_actor", "m9-actor-1", "https://example.org/sv/actors/m9-actor-1",
                     "https://example.org/actors/m9-actor-1"),
        "actor_region": ("actor_registry_actor", "m9-actor-2", "https://example.org/data/pt_BR/actors/m9-actor-2",
                         "https://example.org/data/actors/m9-actor-2"),
        "actor_own": ("actor_registry_actor", "m9-actor-3", "https://example.org/sv/actors/someone-else",
                      "https://example.org/sv/actors/someone-else"),
        "actor_taken": ("actor_registry_actor", "m9-actor-4", "https://example.org/sv/actors/m9-actor-4",
                        "https://example.org/sv/actors/m9-actor-4"),
        "actor_holder": ("actor_registry_actor", "m9-actor-5", "https://example.org/actors/m9-actor-4",
                         "https://example.org/actors/m9-actor-4"),
        "actor_root_path": ("actor_registry_actor", "m9-actor-6", "https://example.org/geo/actors/m9-actor-6",
                            "https://example.org/geo/actors/m9-actor-6"),
        "actor_lang_first": ("actor_registry_actor", "m9-actor-7", "https://example.org/sv/data/actors/m9-actor-7",
                             "https://example.org/data/actors/m9-actor-7"),
        "actor_three_parts": ("actor_registry_actor", "m9-actor-8", "https://example.org/zh_Hant_TW/actors/m9-actor-8",
                              "https://example.org/actors/m9-actor-8"),
        "actor_short_host": ("actor_registry_actor", "m9-actor-9", "http://app/actors/m9-actor-9",
                             "http://app/actors/m9-actor-9"),
        "actor_taken_by_cp": ("actor_registry_actor", "m9-actor-10", "https://example.org/sv/actors/m9-actor-10",
                              "https://example.org/sv/actors/m9-actor-10"),
        "cp_holder": ("contactpoints_contact_point", "m9-cp-3", "https://example.org/actors/m9-actor-10",
                      "https://example.org/actors/m9-actor-10"),
        "cp_sv": ("contactpoints_contact_point", "m9-cp-1", "https://example.org/sv/contactpoints/m9-cp-1",
                  "https://example.org/contactpoints/m9-cp-1"),
        "cp_plain": ("contactpoints_contact_point", "m9-cp-2", "https://example.org/contactpoints/m9-cp-2",
                     "https://example.org/contactpoints/m9-cp-2"),
    }
    _run_migrations("actor_registry", "actor_registry_008", forward=False)
    now = datetime.utcnow()
    for table, row_id, before, _after in rows.values():
        extra = ", actor_kind" if table == "actor_registry_actor" else ""
        value = ", 'organization'" if extra else ""
        ckan_model.Session.execute(text(
            f"INSERT INTO {table} (id, name, uri, active, created, modified{extra}) "
            f"VALUES (:id, :id, :uri, true, :now, :now{value})"), {"id": row_id, "uri": before, "now": now})
    ckan_model.Session.commit()

    _run_migrations("actor_registry", "head", forward=True)
    assert current_revision("actor_registry") == "actor_registry_010 (head)"
    for key, (table, row_id, _before, after) in rows.items():
        uri = ckan_model.Session.execute(text(f"SELECT uri FROM {table} WHERE id = :id"), {"id": row_id}).scalar()
        assert uri == after, key


def test_migration_010_translation_tables_can_be_removed_and_added_again():
    tables = {"actor_registry_actor_translation", "actor_registry_contact_point_translation"}
    assert tables <= _table_names()
    _run_migrations("actor_registry", "actor_registry_009", forward=False)
    assert not tables & _table_names()
    _run_migrations("actor_registry", "head", forward=True)
    assert current_revision("actor_registry") == "actor_registry_010 (head)"
    assert tables <= _table_names()
