"""Increase team_code columns from VARCHAR(5) to VARCHAR(10) — needed for gb-eng, gb-sct

Revision ID: 0006
Revises: 0005
Create Date: 2026-01-06 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("matches") as batch_op:
        batch_op.alter_column("team1_code", type_=sa.String(10), existing_type=sa.String(5))
        batch_op.alter_column("team2_code", type_=sa.String(10), existing_type=sa.String(5))


def downgrade() -> None:
    with op.batch_alter_table("matches") as batch_op:
        batch_op.alter_column("team1_code", type_=sa.String(5), existing_type=sa.String(10))
        batch_op.alter_column("team2_code", type_=sa.String(5), existing_type=sa.String(10))
