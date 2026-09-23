"""Add competitions table; scope phases/matches/leagues/user_badges to a competition

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-21 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    # ── competitions ─────────────────────────────────────────────────────────
    op.create_table(
        "competitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="'draft'"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("points_outcome", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("points_goal_diff", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("points_goal_home", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("points_goal_away", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("joker_bonus", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("joker_penalty", sa.Integer(), nullable=False, server_default="-5"),
        sa.Column("jokers_per_phase", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_competitions_name"),
        if_not_exists=True,
    )

    # WC2026 is factually finished (season report already produced) — every
    # existing row gets attributed to this single competition below.
    op.execute("""
        INSERT INTO competitions (name, status, finished_at)
        VALUES (
            'World Cup 2026',
            'finished',
            (SELECT MAX(finished_at) FROM matches)
        )
    """)

    # ── phases ───────────────────────────────────────────────────────────────
    with op.batch_alter_table("phases") as batch_op:
        batch_op.add_column(sa.Column("competition_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("is_group_stage", sa.Boolean(), nullable=False, server_default="false")
        )
        batch_op.add_column(
            sa.Column("point_multiplier", sa.Numeric(4, 2), nullable=False, server_default="1.00")
        )

    op.execute("""
        UPDATE phases
        SET competition_id = (SELECT id FROM competitions WHERE name = 'World Cup 2026')
    """)
    op.execute("""
        UPDATE phases
        SET is_group_stage = true
        WHERE order_index IN (1, 2, 3)
    """)

    with op.batch_alter_table("phases") as batch_op:
        batch_op.alter_column("competition_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_phases_competition_id", "competitions", ["competition_id"], ["id"]
        )

    # ── matches ──────────────────────────────────────────────────────────────
    with op.batch_alter_table("matches") as batch_op:
        batch_op.add_column(sa.Column("competition_id", sa.Integer(), nullable=True))

    if dialect == "postgresql":
        op.execute("""
            UPDATE matches
            SET competition_id = phases.competition_id
            FROM phases
            WHERE matches.phase_id = phases.id
        """)
    else:
        op.execute("""
            UPDATE matches
            SET competition_id = (
                SELECT competition_id FROM phases WHERE phases.id = matches.phase_id
            )
        """)

    with op.batch_alter_table("matches") as batch_op:
        batch_op.alter_column("competition_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_matches_competition_id", "competitions", ["competition_id"], ["id"]
        )

    # ── leagues ──────────────────────────────────────────────────────────────
    with op.batch_alter_table("leagues") as batch_op:
        batch_op.add_column(sa.Column("competition_id", sa.Integer(), nullable=True))

    op.execute("""
        UPDATE leagues
        SET competition_id = (SELECT id FROM competitions WHERE name = 'World Cup 2026')
    """)

    with op.batch_alter_table("leagues") as batch_op:
        batch_op.alter_column("competition_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_leagues_competition_id", "competitions", ["competition_id"], ["id"]
        )

    # League names only need to be unique within a single competition, so a
    # name can be reused once its original competition is archived.
    with op.batch_alter_table("leagues") as batch_op:
        batch_op.drop_constraint("uq_leagues_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_leagues_name_competition", ["name", "competition_id"]
        )

    # ── user_badges: add competition_id + rebuild unique constraint ──────────
    if dialect == "postgresql":
        op.add_column(
            "user_badges",
            sa.Column("competition_id", sa.Integer(), sa.ForeignKey("competitions.id"),
                      nullable=True),
        )
        op.execute("""
            UPDATE user_badges
            SET competition_id = (SELECT id FROM competitions WHERE name = 'World Cup 2026')
        """)
        op.alter_column("user_badges", "competition_id", existing_type=sa.Integer(), nullable=False)
        op.drop_constraint("uq_user_badge", "user_badges", type_="unique")
        op.create_unique_constraint(
            "uq_user_badge",
            "user_badges",
            ["user_id", "badge_code", "match_id", "league_id", "competition_id"],
        )
    else:
        # SQLite: recreate the table (no ALTER COLUMN / constraint support)
        op.execute("""
            CREATE TABLE IF NOT EXISTS user_badges_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                badge_code VARCHAR(50) NOT NULL,
                match_id INTEGER REFERENCES matches(id),
                league_id INTEGER REFERENCES leagues(id),
                awarded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                competition_id INTEGER NOT NULL REFERENCES competitions(id),
                UNIQUE(user_id, badge_code, match_id, league_id, competition_id)
            )
        """)
        op.execute("""
            INSERT INTO user_badges_new
                (id, user_id, badge_code, match_id, league_id, awarded_at, is_active, competition_id)
            SELECT
                id, user_id, badge_code, match_id, league_id, awarded_at, is_active,
                (SELECT id FROM competitions WHERE name = 'World Cup 2026')
            FROM user_badges
        """)
        op.execute("DROP TABLE user_badges")
        op.execute("ALTER TABLE user_badges_new RENAME TO user_badges")

    # ── partial unique index: only one active competition at a time ─────────
    op.create_index(
        "uq_competitions_active",
        "competitions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    op.drop_index("uq_competitions_active", "competitions")

    if dialect == "postgresql":
        op.drop_constraint("uq_user_badge", "user_badges", type_="unique")
        op.drop_column("user_badges", "competition_id")
        op.create_unique_constraint(
            "uq_user_badge", "user_badges", ["user_id", "badge_code", "match_id", "league_id"]
        )
    else:
        op.execute("""
            CREATE TABLE user_badges_old (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                badge_code VARCHAR(50) NOT NULL,
                match_id INTEGER REFERENCES matches(id),
                league_id INTEGER REFERENCES leagues(id),
                awarded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                UNIQUE(user_id, badge_code, match_id, league_id)
            )
        """)
        op.execute("""
            INSERT INTO user_badges_old
                (id, user_id, badge_code, match_id, league_id, awarded_at, is_active)
            SELECT id, user_id, badge_code, match_id, league_id, awarded_at, is_active
            FROM user_badges
        """)
        op.execute("DROP TABLE user_badges")
        op.execute("ALTER TABLE user_badges_old RENAME TO user_badges")

    with op.batch_alter_table("leagues") as batch_op:
        batch_op.drop_constraint("uq_leagues_name_competition", type_="unique")
        batch_op.drop_constraint("fk_leagues_competition_id", type_="foreignkey")
        batch_op.drop_column("competition_id")
        batch_op.create_unique_constraint("uq_leagues_name", ["name"])

    with op.batch_alter_table("matches") as batch_op:
        batch_op.drop_constraint("fk_matches_competition_id", type_="foreignkey")
        batch_op.drop_column("competition_id")

    with op.batch_alter_table("phases") as batch_op:
        batch_op.drop_constraint("fk_phases_competition_id", type_="foreignkey")
        batch_op.drop_column("point_multiplier")
        batch_op.drop_column("is_group_stage")
        batch_op.drop_column("competition_id")

    op.drop_table("competitions")
