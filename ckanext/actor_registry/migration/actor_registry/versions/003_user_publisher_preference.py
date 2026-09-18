"""Store each CKAN user's most recently used publisher.

Revision ID: actor_registry_003
Revises: actor_registry_002
"""

from alembic import op
import sqlalchemy as sa


revision = "actor_registry_003"
down_revision = "actor_registry_002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "actor_registry_user_preference",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("publisher_actor_id", sa.String(length=36), nullable=True),
        sa.Column("modified", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
        sa.ForeignKeyConstraint(
            ["publisher_actor_id"], ["actor_registry_actor.id"],
            name="actor_registry_user_preference_actor_fkey", ondelete="SET NULL",
        ),
    )


def downgrade():
    op.drop_table("actor_registry_user_preference")
