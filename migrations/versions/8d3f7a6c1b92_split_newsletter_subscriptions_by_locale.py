"""split_newsletter_subscriptions_by_locale

Revision ID: 8d3f7a6c1b92
Revises: 02daa0cf0002
Create Date: 2026-05-23 14:25:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8d3f7a6c1b92"
down_revision: Union[str, Sequence[str], None] = "02daa0cf0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE subscribers
        SET locale = 'sr'
        WHERE locale IS NULL OR locale = '';

        ALTER TABLE subscribers
        ALTER COLUMN locale SET DEFAULT 'sr',
        ALTER COLUMN locale SET NOT NULL;

        ALTER TABLE subscribers
        DROP CONSTRAINT IF EXISTS subscribers_pkey;

        ALTER TABLE subscribers
        DROP CONSTRAINT IF EXISTS subscribers_email_key;

        DROP INDEX IF EXISTS subscribers_email_key;

        ALTER TABLE subscribers
        ADD CONSTRAINT subscribers_pkey PRIMARY KEY (email, locale);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM subscribers s
        USING subscribers newer
        WHERE s.email = newer.email
          AND s.locale <> newer.locale
          AND s.created_at < newer.created_at;

        ALTER TABLE subscribers
        DROP CONSTRAINT IF EXISTS subscribers_pkey;

        ALTER TABLE subscribers
        ALTER COLUMN locale DROP NOT NULL;

        ALTER TABLE subscribers
        ADD CONSTRAINT subscribers_pkey PRIMARY KEY (email);
        """
    )
