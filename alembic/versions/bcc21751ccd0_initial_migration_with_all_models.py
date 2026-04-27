"""Initial migration with all models

Revision ID: bcc21751ccd0
Revises: e87c691235ea
Create Date: 2026-04-25 19:55:09.219232
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bcc21751ccd0'
down_revision = 'e87c691235ea'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('plan_claims', sa.Column('amount_paid', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('plan_claims', 'amount_paid')
