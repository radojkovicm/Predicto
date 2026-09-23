"""Add is_active field to user_badges to track badge lifecycle

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-18 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_badges") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.sql.expression.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("user_badges") as batch_op:
        batch_op.drop_column("is_active")
