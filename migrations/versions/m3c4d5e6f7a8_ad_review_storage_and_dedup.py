"""ad campaigns: banner bytes in the DB, manual review, per-visitor impression dedup

Revision ID: m3c4d5e6f7a8
Revises: l2b3c4d5e6f7
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "l2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "advertising_campaigns" in tables:
        existing = {c["name"] for c in inspector.get_columns("advertising_campaigns")}
        # Banners live in the DB so every serving host (phone, Shield) can
        # return them; the old per-host upload dir split them across hosts.
        if "image_data" not in existing:
            op.add_column("advertising_campaigns", sa.Column("image_data", sa.LargeBinary()))
        if "image_mime" not in existing:
            op.add_column("advertising_campaigns", sa.Column("image_mime", sa.Text()))
        # A paid campaign serves only after an admin approves it.
        if "approved_at" not in existing:
            op.add_column("advertising_campaigns", sa.Column("approved_at", sa.DateTime(timezone=True)))
        if "review_note" not in existing:
            op.add_column("advertising_campaigns", sa.Column("review_note", sa.Text()))

    if "ad_impression_seen" not in tables:
        op.create_table(
            "ad_impression_seen",
            sa.Column("campaign_id", sa.Text(), nullable=False),
            sa.Column("visitor_hash", sa.Text(), nullable=False),
            sa.Column("day", sa.Date(), nullable=False),
            sa.PrimaryKeyConstraint("campaign_id", "visitor_hash", "day"),
        )
        op.create_index("ix_ad_impression_seen_day", "ad_impression_seen", ["day"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_ad_impression_seen_day", table_name="ad_impression_seen")
    op.drop_table("ad_impression_seen")
    op.drop_column("advertising_campaigns", "review_note")
    op.drop_column("advertising_campaigns", "approved_at")
    op.drop_column("advertising_campaigns", "image_mime")
    op.drop_column("advertising_campaigns", "image_data")
