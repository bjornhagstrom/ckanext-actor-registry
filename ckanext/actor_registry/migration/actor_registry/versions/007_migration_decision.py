"""Log of the decisions made in "Migrate to Actor Registry".

One row per dataset and decision (linked, skipped, unskipped), append-only:
the latest row for a dataset is its current state. The fingerprint is a hash
of the dataset's Maintainer/Author values when the decision was made, so a
later change to those values can be detected.

Revision ID: actor_registry_007
Revises: actor_registry_006
"""

from alembic import op
import sqlalchemy as sa


revision = "actor_registry_007"
down_revision = "actor_registry_006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "actor_registry_migration_decision",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("contact_point_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("created", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "actor_registry_migration_decision_package_idx",
        "actor_registry_migration_decision", ["package_id", "created"], unique=False,
    )


def downgrade():
    op.drop_index(
        "actor_registry_migration_decision_package_idx",
        table_name="actor_registry_migration_decision",
    )
    op.drop_table("actor_registry_migration_decision")
