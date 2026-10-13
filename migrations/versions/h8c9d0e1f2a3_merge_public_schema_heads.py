"""merge legacy schema lineage with the Macedonian runtime lineage

Revision ID: h8c9d0e1f2a3
Revises: 1f0627776d70, 02c58f04407a
"""

from collections.abc import Sequence

revision: str = "h8c9d0e1f2a3"
down_revision: str | Sequence[str] | None = (
    "1f0627776d70",
    "02c58f04407a",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    raise NotImplementedError("Schema merge is not reversible")
