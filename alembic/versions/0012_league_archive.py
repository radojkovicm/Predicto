"""Add archived_at to leagues — lets one league retire early while its
competition (and its other leagues) stay active.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-22 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("leagues") as batch_op:
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("leagues") as batch_op:
        batch_op.drop_column("archived_at")
