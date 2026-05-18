"""add_lang_to_daily_briefings

Revision ID: b7ba54d8a217
Revises: c095399af315
Create Date: 2026-05-14 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7ba54d8a217"
down_revision = "c095399af315"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add lang column with server default 'sr'
    op.add_column("daily_briefings", sa.Column("lang", sa.String(length=5), nullable=False, server_default="sr"))

    # 2. Update primary key to be (date, lang)
    # First drop existing primary key constraint
    op.drop_constraint("daily_briefings_pkey", "daily_briefings", type_="primary")
    # Then create new primary key
    op.create_primary_key("daily_briefings_pkey", "daily_briefings", ["date", "lang"])


def downgrade():
    op.drop_constraint("daily_briefings_pkey", "daily_briefings", type_="primary")
    op.drop_column("daily_briefings", "lang")
    op.create_primary_key("daily_briefings_pkey", "daily_briefings", ["date"])
