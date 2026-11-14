import pytest


@pytest.fixture
def actor_registry_db(clean_db, migrate_db_for):
    """Create the extension tables in CKAN's isolated test database."""
    migrate_db_for("actor_registry")


@pytest.fixture
def restore_option():
    """Reset the setting that closes the migration around a test:
    config_option_update changes the running config, and CKAN keeps the
    first value it saw in a process-wide cache."""
    from ckan.common import config
    from ckan.lib import app_globals

    from ckanext.actor_registry.helpers import LEGACY_CONTACT_FIELDS_OPTION

    def reset():
        app_globals._CONFIG_CACHE.pop(LEGACY_CONTACT_FIELDS_OPTION, None)
        config.pop(LEGACY_CONTACT_FIELDS_OPTION, None)

    reset()
    yield
    reset()
