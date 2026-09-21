"""Enforce unique (identifier_scheme, identifier) among active actors.

Revision ID: actor_registry_006
Revises: actor_registry_005

Partial unique index: only active actors with BOTH fields filled in are
constrained. Merged/retired actors keep their identifier (it is history,
and the survivor may legitimately adopt it), and identifier/scheme are
optional as a pair.

If existing data already contains duplicates the upgrade fails with an
IntegrityError; resolve them (merge the duplicate actors) and re-run.
"""

from alembic import op


revision = "actor_registry_006"
down_revision = "actor_registry_005"
branch_labels = None
depends_on = None

INDEX_NAME = "actor_registry_actor_identifier_uq"


def upgrade():
    op.execute(
        "CREATE UNIQUE INDEX {name} ON actor_registry_actor "
        "(identifier_scheme, identifier) "
        "WHERE active AND coalesce(identifier, '') <> '' "
        "AND coalesce(identifier_scheme, '') <> ''".format(name=INDEX_NAME)
    )


def downgrade():
    op.execute("DROP INDEX {name}".format(name=INDEX_NAME))
