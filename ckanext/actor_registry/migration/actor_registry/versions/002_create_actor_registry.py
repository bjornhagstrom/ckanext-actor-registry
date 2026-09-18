"""Add reusable actors and link contact points to actors.

Revision ID: actor_registry_002
Revises: contactpoints_001
"""

from alembic import op
import sqlalchemy as sa


revision = "actor_registry_002"
down_revision = "contactpoints_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "actor_registry_actor",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("actor_kind", sa.String(length=30), nullable=False, server_default="organization"),
        sa.Column("actor_type", sa.Text(), nullable=True),
        sa.Column("identifier", sa.String(length=255), nullable=True),
        sa.Column("identifier_scheme", sa.String(length=255), nullable=True),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("modified", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uri"),
    )
    op.add_column("contactpoints_contact_point", sa.Column("actor_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "contactpoints_contact_point_actor_id_fkey",
        "contactpoints_contact_point", "actor_registry_actor",
        ["actor_id"], ["id"], ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("contactpoints_contact_point_actor_id_fkey", "contactpoints_contact_point", type_="foreignkey")
    op.drop_column("contactpoints_contact_point", "actor_id")
    op.drop_table("actor_registry_actor")
