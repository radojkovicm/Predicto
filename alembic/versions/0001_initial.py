"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "phases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("joker_allowed", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phase_id", sa.Integer(), sa.ForeignKey("phases.id"), nullable=False),
        sa.Column("team1_code", sa.String(5), nullable=False),
        sa.Column("team1_name", sa.String(50), nullable=False),
        sa.Column("team2_code", sa.String(5), nullable=False),
        sa.Column("team2_name", sa.String(50), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_goals1", sa.Integer(), nullable=True),
        sa.Column("result_goals2", sa.Integer(), nullable=True),
        sa.Column("is_finished", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matches_kickoff_utc", "matches", ["kickoff_utc"])
    op.create_index("ix_matches_phase_id", "matches", ["phase_id"])

    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("pred_goals1", sa.Integer(), nullable=False),
        sa.Column("pred_goals2", sa.Integer(), nullable=False),
        sa.Column("is_joker", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "match_id", name="uq_prediction_user_match"),
    )
    op.create_index("ix_predictions_user_id", "predictions", ["user_id"])
    op.create_index("ix_predictions_match_id", "predictions", ["match_id"])

    op.create_table(
        "result_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("old_goals1", sa.Integer(), nullable=True),
        sa.Column("old_goals2", sa.Integer(), nullable=True),
        sa.Column("new_goals1", sa.Integer(), nullable=True),
        sa.Column("new_goals2", sa.Integer(), nullable=True),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "prediction_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("old_goals1", sa.Integer(), nullable=True),
        sa.Column("old_goals2", sa.Integer(), nullable=True),
        sa.Column("new_goals1", sa.Integer(), nullable=False),
        sa.Column("new_goals2", sa.Integer(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_badges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("badge_code", sa.String(50), nullable=False),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=True),
        sa.Column("awarded_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "badge_code", "match_id", name="uq_user_badge"),
    )
    # Partial unique index for aggregate badges — only on PostgreSQL
    # (SQLite handles NULL uniqueness differently; badge_service checks before inserting anyway)
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "uq_user_badge_aggregate",
            "user_badges",
            ["user_id", "badge_code"],
            unique=True,
            postgresql_where=sa.text("match_id IS NULL"),
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("uq_user_badge_aggregate", "user_badges")
    op.drop_table("user_badges")
    op.drop_table("prediction_log")
    op.drop_table("result_log")
    op.drop_index("ix_predictions_match_id")
    op.drop_index("ix_predictions_user_id")
    op.drop_table("predictions")
    op.drop_index("ix_matches_phase_id")
    op.drop_index("ix_matches_kickoff_utc")
    op.drop_table("matches")
    op.drop_table("phases")
    op.drop_table("users")
