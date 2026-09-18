"""Store recently used contact points per CKAN user.

Revision ID: actor_registry_004
Revises: actor_registry_003
"""

from alembic import op
import sqlalchemy as sa


revision = "actor_registry_004"
down_revision = "actor_registry_003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "actor_registry_recent_contact_point",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("contact_point_id", sa.String(length=36), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "contact_point_id"),
        sa.ForeignKeyConstraint(
            ["contact_point_id"], ["contactpoints_contact_point.id"],
            name="actor_registry_recent_contact_point_contact_fkey", ondelete="CASCADE",
        ),
    )
    op.create_index(
        "actor_registry_recent_contact_point_user_used_idx",
        "actor_registry_recent_contact_point", ["user_id", "used_at"], unique=False,
    )


def downgrade():
    op.drop_index(
        "actor_registry_recent_contact_point_user_used_idx",
        table_name="actor_registry_recent_contact_point",
    )
    op.drop_table("actor_registry_recent_contact_point")
