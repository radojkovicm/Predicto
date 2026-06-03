"""Add leagues + user_leagues; add league_id to user_badges

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-02 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    # ── leagues ──────────────────────────────────────────────────────────────
    op.create_table(
        "leagues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("join_code", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_leagues_name"),
        sa.UniqueConstraint("join_code", name="uq_leagues_join_code"),
        if_not_exists=True,
    )

    # ── user_leagues ─────────────────────────────────────────────────────────
    op.create_table(
        "user_leagues",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("leagues.id"), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "league_id"),
        if_not_exists=True,
    )

    # ── user_badges: add league_id + update unique constraint ────────────────
    if dialect == "postgresql":
        op.add_column("user_badges",
                      sa.Column("league_id", sa.Integer(),
                                sa.ForeignKey("leagues.id"), nullable=True))
        op.drop_constraint("uq_user_badge", "user_badges", type_="unique")
        op.create_unique_constraint(
            "uq_user_badge",
            "user_badges",
            ["user_id", "badge_code", "match_id", "league_id"],
        )
    else:
        # SQLite: recreate the table (no ALTER COLUMN support)
        op.execute("""
            CREATE TABLE IF NOT EXISTS user_badges_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                badge_code VARCHAR(50) NOT NULL,
                match_id INTEGER REFERENCES matches(id),
                league_id INTEGER REFERENCES leagues(id),
                awarded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, badge_code, match_id, league_id)
            )
        """)
        op.execute("""
            INSERT OR IGNORE INTO user_badges_new
                (id, user_id, badge_code, match_id, league_id, awarded_at)
            SELECT id, user_id, badge_code, match_id, NULL, awarded_at
            FROM user_badges
        """)
        op.execute("DROP TABLE user_badges")
        op.execute("ALTER TABLE user_badges_new RENAME TO user_badges")


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "postgresql":
        op.drop_constraint("uq_user_badge", "user_badges", type_="unique")
        op.drop_column("user_badges", "league_id")
        op.create_unique_constraint(
            "uq_user_badge", "user_badges", ["user_id", "badge_code", "match_id"]
        )
    else:
        op.execute("""
            CREATE TABLE user_badges_old (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                badge_code VARCHAR(50) NOT NULL,
                match_id INTEGER REFERENCES matches(id),
                awarded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, badge_code, match_id)
            )
        """)
        op.execute("""
            INSERT INTO user_badges_old (id, user_id, badge_code, match_id, awarded_at)
            SELECT id, user_id, badge_code, match_id, awarded_at FROM user_badges
        """)
        op.execute("DROP TABLE user_badges")
        op.execute("ALTER TABLE user_badges_old RENAME TO user_badges")

    op.drop_table("user_leagues")
    op.drop_table("leagues")
