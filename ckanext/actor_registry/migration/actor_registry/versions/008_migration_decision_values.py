"""Keep the Maintainer/Author values a migration decision was made on.

The fingerprint tells that the values changed; the stored values let the
migration page show what they were. Older rows have none (NULL).

Revision ID: actor_registry_008
Revises: actor_registry_007
"""

from alembic import op
import sqlalchemy as sa


revision = "actor_registry_008"
down_revision = "actor_registry_007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("actor_registry_migration_decision",
                  sa.Column("source_values", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("actor_registry_migration_decision", "source_values")
