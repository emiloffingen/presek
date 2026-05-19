"""recover_delivery_tables

Revision ID: 472c0aa46965
Revises: 24434f8a57fc
Create Date: 2026-05-19 09:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "472c0aa46965"
down_revision: Union[str, Sequence[str], None] = "24434f8a57fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 6. Reader Profiles & Subscriptions
    op.execute(
        """CREATE TABLE IF NOT EXISTS synced_reader_profiles (
        sync_token TEXT PRIMARY KEY,
        profile_data JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS synced_delivery_subscriptions (
        sync_token TEXT PRIMARY KEY REFERENCES synced_reader_profiles(sync_token) ON DELETE CASCADE,
        channel TEXT DEFAULT 'ntfy',
        target TEXT DEFAULT '',
        morning_briefing BOOLEAN DEFAULT TRUE,
        weekly_digest BOOLEAN DEFAULT FALSE,
        breaking_topics BOOLEAN DEFAULT FALSE,
        breaking_sources BOOLEAN DEFAULT FALSE,
        is_active BOOLEAN DEFAULT FALSE,
        last_morning_sent_at TIMESTAMP,
        last_weekly_sent_at TIMESTAMP,
        last_breaking_sent_at TIMESTAMP,
        last_alert_cluster_ids JSONB DEFAULT '[]'::jsonb,
        last_alert_context JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""
    )

    # 7. Tracking & Logs
    op.execute(
        """CREATE TABLE IF NOT EXISTS delivery_tracking_events (
        id SERIAL PRIMARY KEY,
        sync_token TEXT REFERENCES synced_reader_profiles(sync_token) ON DELETE CASCADE,
        parent_event_id INTEGER REFERENCES delivery_tracking_events(id) ON DELETE SET NULL,
        event_type TEXT NOT NULL,
        delivery_kind TEXT NOT NULL,
        channel TEXT DEFAULT 'ntfy',
        target TEXT DEFAULT '',
        cluster_id TEXT,
        metadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_delivery_tracking_sync_created ON delivery_tracking_events(sync_token, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_delivery_tracking_event_kind_created ON delivery_tracking_events(event_type, delivery_kind, created_at DESC)"
    )


def downgrade() -> None:
    pass
