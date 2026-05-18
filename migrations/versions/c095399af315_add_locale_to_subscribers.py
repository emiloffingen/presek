"""add_locale_to_subscribers

Revision ID: c095399af315
Revises: f631fc2a7880
Create Date: 2026-05-14 11:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c095399af315"
down_revision = "238ae1b3d204"
branch_labels = None
depends_on = None


def upgrade():
    # Add locale to subscribers
    op.add_column("subscribers", sa.Column("locale", sa.String(length=5), nullable=True, server_default="sr"))

    # Add locale to synced_delivery_subscriptions
    op.add_column(
        "synced_delivery_subscriptions", sa.Column("locale", sa.String(length=5), nullable=True, server_default="sr")
    )


def downgrade():
    op.drop_column("synced_delivery_subscriptions", "locale")
    op.drop_column("subscribers", "locale")
