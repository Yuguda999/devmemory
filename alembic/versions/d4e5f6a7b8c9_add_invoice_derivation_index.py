"""add_invoice_derivation_index

Adds the per-invoice HD address index (unique) that backs unique-address payment
identification.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-14 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('invoices') as batch:
        # server_default only to satisfy NOT NULL for any pre-existing rows; new
        # rows always set an explicit index via next_derivation_index().
        batch.add_column(
            sa.Column('derivation_index', sa.Integer(), nullable=False, server_default='0')
        )
        batch.create_unique_constraint('uq_invoices_derivation_index', ['derivation_index'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('invoices') as batch:
        batch.drop_constraint('uq_invoices_derivation_index', type_='unique')
        batch.drop_column('derivation_index')
