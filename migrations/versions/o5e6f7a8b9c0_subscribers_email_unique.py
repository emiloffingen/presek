"""unique constraint on subscribers.email

The /newsletter/subscribe route relies on ON CONFLICT (email), but the table had
no unique constraint, so every signup errored. Dedupe and enforce uniqueness.

Revision ID: o5e6f7a8b9c0
Revises: n4d5e6f7a8b9
"""

from typing import Sequence, Union

from alembic import op

revision: str = "o5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "n4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM subscribers a USING subscribers b WHERE a.id > b.id AND a.email = b.email")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS subscribers_email_key ON subscribers (email)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS subscribers_email_key")
