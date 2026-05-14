from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_language_to_daily_briefings'
down_revision = 'b7ba54d8a217'
branch_labels = None
depends_on = None

def upgrade():
    # Add language column to daily_briefings table
    op.add_column('daily_briefings', sa.Column('lang', sa.String(length=2), nullable=True))
    
    # Set default language to 'sr' for existing records
    op.execute("UPDATE daily_briefings SET lang = 'sr' WHERE lang IS NULL")
    
    # Make the column non-nullable
    op.alter_column('daily_briefings', 'lang', nullable=False)
    
    # Add index for faster language-based queries
    op.create_index(op.f('ix_daily_briefings_lang'), 'daily_briefings', ['lang'])
    
    # Make the primary key composite (date + lang) to allow multiple briefings per day
    op.drop_constraint('daily_briefings_pkey', 'daily_briefings', type_='primary')
    op.create_primary_key('daily_briefings_pkey', 'daily_briefings', ['date', 'lang'])

def downgrade():
    # Revert to simple date-based primary key
    op.drop_constraint('daily_briefings_pkey', 'daily_briefings', type_='primary')
    op.create_primary_key('daily_briefings_pkey', 'daily_briefings', ['date'])
    
    # Drop the language column
    op.drop_column('daily_briefings', 'lang')