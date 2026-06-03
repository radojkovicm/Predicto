"""Add is_visible to matches

Revision ID: 0004
Revises: 0003
Create Date: 2026-01-04 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("matches") as batch_op:
        batch_op.add_column(
            sa.Column("is_visible", sa.Boolean(), nullable=False, server_default="false")
        )
    # All existing matches are already imported and ready — make them visible
    op.execute("UPDATE matches SET is_visible = true")


def downgrade() -> None:
    with op.batch_alter_table("matches") as batch_op:
        batch_op.drop_column("is_visible")
