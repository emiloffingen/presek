"""init

Revision ID: 438101a6575f
Revises:
Create Date: 2026-04-26 14:06:02.364639

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "438101a6575f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
