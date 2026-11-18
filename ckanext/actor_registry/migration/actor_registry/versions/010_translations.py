"""Names (and a publisher's description) in more languages than the default one.

Revision ID: actor_registry_010
Revises: actor_registry_009
"""

from alembic import op
import sqlalchemy as sa


revision = "actor_registry_010"
down_revision = "actor_registry_009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "actor_registry_actor_translation",
        sa.Column("actor_id", sa.String(36),
                  sa.ForeignKey("actor_registry_actor.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("lang", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_table(
        "actor_registry_contact_point_translation",
        sa.Column("contact_point_id", sa.String(36),
                  sa.ForeignKey("contactpoints_contact_point.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("lang", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
    )


def downgrade():
    op.drop_table("actor_registry_contact_point_translation")
    op.drop_table("actor_registry_actor_translation")
