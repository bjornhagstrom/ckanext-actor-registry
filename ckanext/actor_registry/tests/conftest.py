import pytest


@pytest.fixture
def actor_registry_db(clean_db, migrate_db_for):
    """Create the extension tables in CKAN's isolated test database."""
    migrate_db_for("actor_registry")
