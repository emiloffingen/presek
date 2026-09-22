"""add stripe payment intent and idempotency key to advertising campaigns

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "i9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "advertising_campaigns" not in set(inspector.get_table_names()):
        return

    existing = {c["name"] for c in inspector.get_columns("advertising_campaigns")}
    if "stripe_payment_intent" not in existing:
        op.add_column(
            "advertising_campaigns", sa.Column("stripe_payment_intent", sa.Text())
        )
    if "idempotency_key" not in existing:
        op.add_column(
            "advertising_campaigns", sa.Column("idempotency_key", sa.Text())
        )

    indexes = {i["name"] for i in inspector.get_indexes("advertising_campaigns")}
    if "ix_advertising_campaigns_stripe_payment_intent" not in indexes:
        op.create_index(
            "ix_advertising_campaigns_stripe_payment_intent",
            "advertising_campaigns",
            ["stripe_payment_intent"],
        )
    if "ux_advertising_campaigns_idempotency_key" not in indexes:
        op.create_index(
            "ux_advertising_campaigns_idempotency_key",
            "advertising_campaigns",
            ["idempotency_key"],
            unique=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ux_advertising_campaigns_idempotency_key",
        table_name="advertising_campaigns",
    )
    op.drop_index(
        "ix_advertising_campaigns_stripe_payment_intent",
        table_name="advertising_campaigns",
    )
    op.drop_column("advertising_campaigns", "idempotency_key")
    op.drop_column("advertising_campaigns", "stripe_payment_intent")
