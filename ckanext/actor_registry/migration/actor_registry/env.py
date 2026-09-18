from alembic import context
from sqlalchemy import engine_from_config, pool

from ckan.model import init_model
from ckan.model.meta import metadata


config = context.config
target_metadata = metadata
# Keep the original version table so installations upgrading from
# ckanext-contactpoints continue from their existing migration state.
version_table = "contactpoints_alembic_version"


def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        version_table=version_table,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        init_model(connectable)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=version_table,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
