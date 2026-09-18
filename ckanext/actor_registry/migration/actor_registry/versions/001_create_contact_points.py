"""Create reusable contact points.

Revision ID: contactpoints_001
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "contactpoints_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contactpoints_contact_point",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=100), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("modified", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uri"),
    )


def downgrade():
    op.drop_table("contactpoints_contact_point")
