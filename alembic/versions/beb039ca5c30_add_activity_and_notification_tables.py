"""add activity and notification tables"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'beb039ca5c30'
down_revision: Union[str, Sequence[str], None] = '24417ff15934'
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        'activity_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('entity_type', sa.String(30), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False
        ),
    )

    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column('title', sa.String(100), nullable=False),
        sa.Column('message', sa.String(500), nullable=False),
        sa.Column(
            'type',
            sa.String(30),
            server_default='info',
            nullable=False
        ),
        sa.Column(
            'is_read',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False
        ),
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table('notifications')
    op.drop_table('activity_logs')