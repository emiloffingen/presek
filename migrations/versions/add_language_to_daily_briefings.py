import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "add_language_to_daily_briefings"
down_revision = "b7ba54d8a217"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('daily_briefings')]

    if 'lang' not in columns:
        # Add language column to daily_briefings table
        op.add_column("daily_briefings", sa.Column("lang", sa.String(length=2), nullable=True))

        # Set default language to 'sr' for existing records
        op.execute("UPDATE daily_briefings SET lang = 'sr' WHERE lang IS NULL")

        # Make the column non-nullable
        op.alter_column("daily_briefings", "lang", nullable=False)

    # Add index for faster language-based queries if it doesn't exist
    indexes = [idx['name'] for idx in inspector.get_indexes('daily_briefings')]
    if 'ix_daily_briefings_lang' not in indexes:
        op.create_index("ix_daily_briefings_lang", "daily_briefings", ["lang"])

    # Make the primary key composite (date + lang) to allow multiple briefings per day if not already
    pk_constraint = inspector.get_pk_constraint('daily_briefings')
    pk_cols = pk_constraint.get('constrained_columns', [])
    if 'lang' not in pk_cols:
        try:
            op.drop_constraint("daily_briefings_pkey", "daily_briefings", type_="primary")
        except Exception:
            pass
        op.create_primary_key("daily_briefings_pkey", "daily_briefings", ["date", "lang"])


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('daily_briefings')]

    if 'lang' in columns:
        # Revert to simple date-based primary key
        try:
            op.drop_constraint("daily_briefings_pkey", "daily_briefings", type_="primary")
        except Exception:
            pass
        op.create_primary_key("daily_briefings_pkey", "daily_briefings", ["date"])

        # Drop the index
        indexes = [idx['name'] for idx in inspector.get_indexes('daily_briefings')]
        if 'ix_daily_briefings_lang' in indexes:
            op.drop_index("ix_daily_briefings_lang", "daily_briefings")

        # Drop the language column
        op.drop_column("daily_briefings", "lang")

