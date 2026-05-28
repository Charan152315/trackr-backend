"""Add new fields and constraints for restructuring

Revision ID: 001_restructure_add_fields
Revises: 5855f7f5bd86
Create Date: 2024-01-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_restructure_add_fields'
down_revision = '5855f7f5bd86'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add new fields and indexes"""
    
    # Add upi_verified_at to users
    op.add_column('users', sa.Column(
        'upi_verified_at',
        sa.TIMESTAMP(timezone=True),
        nullable=True
    ))
    
    # Add updated_at to group_expenses
    op.add_column('group_expenses', sa.Column(
        'updated_at',
        sa.TIMESTAMP(timezone=True),
        server_default=sa.func.now(),
        nullable=False
    ))
    
    # Add confirmed_at to settlements
    op.add_column('settlements', sa.Column(
        'confirmed_at',
        sa.TIMESTAMP(timezone=True),
        nullable=True
    ))
    
    # Add rejected_at to settlements
    op.add_column('settlements', sa.Column(
        'rejected_at',
        sa.TIMESTAMP(timezone=True),
        nullable=True
    ))
    
    # Add joined_at to group_members
    op.add_column('group_members', sa.Column(
        'joined_at',
        sa.TIMESTAMP(timezone=True),
        server_default=sa.func.now(),
        nullable=False
    ))
    
    # Create indexes for performance
    op.create_index('idx_owner_created', 'expenses', ['owner_id', 'created_at'])
    op.create_index('idx_group_created', 'group_expenses', ['group_id', 'created_at'])
    op.create_index('idx_user_group', 'group_members', ['user_id', 'group_id'])
    op.create_index('idx_expense_user', 'splits', ['group_expense_id', 'user_id'])
    op.create_index('idx_group_status', 'settlements', ['group_id', 'status'])
    op.create_index('idx_from_to', 'settlements', ['from_user_id', 'to_user_id'])


def downgrade() -> None:
    """Rollback changes"""
    
    op.drop_index('idx_from_to', 'settlements')
    op.drop_index('idx_group_status', 'settlements')
    op.drop_index('idx_expense_user', 'splits')
    op.drop_index('idx_user_group', 'group_members')
    op.drop_index('idx_group_created', 'group_expenses')
    op.drop_index('idx_owner_created', 'expenses')
    
    op.drop_column('group_members', 'joined_at')
    op.drop_column('settlements', 'rejected_at')
    op.drop_column('settlements', 'confirmed_at')
    op.drop_column('group_expenses', 'updated_at')
    op.drop_column('users', 'upi_verified_at')