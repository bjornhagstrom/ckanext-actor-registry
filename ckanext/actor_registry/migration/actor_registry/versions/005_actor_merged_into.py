"""Track soft-retirement of actors merged into another actor.

Revision ID: actor_registry_005
Revises: actor_registry_004
"""

from alembic import op
import sqlalchemy as sa


revision = "actor_registry_005"
down_revision = "actor_registry_004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "actor_registry_actor",
        sa.Column("merged_into_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "actor_registry_actor_merged_into_id_fkey",
        "actor_registry_actor", "actor_registry_actor",
        ["merged_into_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(
        "actor_registry_actor_merged_into_id_idx",
        "actor_registry_actor", ["merged_into_id"], unique=False,
    )


def downgrade():
    op.drop_index(
        "actor_registry_actor_merged_into_id_idx",
        table_name="actor_registry_actor",
    )
    op.drop_constraint(
        "actor_registry_actor_merged_into_id_fkey",
        "actor_registry_actor", type_="foreignkey",
    )
    op.drop_column("actor_registry_actor", "merged_into_id")
