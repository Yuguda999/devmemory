"""add_invoices_and_cardano_fields

Replaces the unused Stripe subscription columns with Cardano payment fields and
adds the ``invoices`` table backing the pull-model ADA payment flow.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'invoices',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('tier', sa.String(length=20), nullable=False),
        sa.Column('amount_lovelace', sa.BigInteger(), nullable=False),
        sa.Column('pay_to_address', sa.String(length=255), nullable=False),
        sa.Column('network', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('tx_hash', sa.String(length=128), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_invoices_user_id'), 'invoices', ['user_id'], unique=False)
    op.create_index(op.f('ix_invoices_status'), 'invoices', ['status'], unique=False)

    # Swap the never-populated Stripe columns for Cardano payment fields.
    with op.batch_alter_table('subscriptions') as batch:
        batch.add_column(sa.Column('last_invoice_id', sa.String(length=36), nullable=True))
        batch.add_column(sa.Column('last_tx_hash', sa.String(length=128), nullable=True))
        batch.drop_column('stripe_customer_id')
        batch.drop_column('stripe_subscription_id')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('subscriptions') as batch:
        batch.add_column(sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True))
        batch.add_column(sa.Column('stripe_customer_id', sa.String(length=255), nullable=True))
        batch.drop_column('last_tx_hash')
        batch.drop_column('last_invoice_id')

    op.drop_index(op.f('ix_invoices_status'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_user_id'), table_name='invoices')
    op.drop_table('invoices')
