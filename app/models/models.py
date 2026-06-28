from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class League(Base):
    __tablename__ = "leagues"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    join_code = Column(String(20), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("User", secondary="user_leagues", back_populates="leagues")


class UserLeague(Base):
    __tablename__ = "user_leagues"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    league_id = Column(Integer, ForeignKey("leagues.id"), primary_key=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    first_name = Column(String(80), nullable=True)
    last_name = Column(String(80), nullable=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    failed_login_attempts = Column(Integer, default=0, nullable=False, server_default="0")
    locked_until = Column(DateTime(timezone=True), nullable=True)

    @property
    def display_name(self) -> str:
        """Full name if set, otherwise username."""
        full = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return full if full else self.username

    leagues = relationship("League", secondary="user_leagues", back_populates="members")
    predictions = relationship("Prediction", back_populates="user", foreign_keys="[Prediction.user_id]")
    badges = relationship("UserBadge", back_populates="user")
    result_changes = relationship("ResultLog", back_populates="changed_by_user")
    prediction_changes_made = relationship(
        "PredictionLog", back_populates="changed_by_user", foreign_keys="[PredictionLog.changed_by]"
    )


class Phase(Base):
    __tablename__ = "phases"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    order_index = Column(Integer, nullable=False)
    joker_allowed = Column(Boolean, default=True, nullable=False, server_default="true")

    matches = relationship("Match", back_populates="phase", order_by="Match.kickoff_utc")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    phase_id = Column(Integer, ForeignKey("phases.id"), nullable=False)
    team1_code = Column(String(10), nullable=False)
    team1_name = Column(String(50), nullable=False)
    team2_code = Column(String(10), nullable=False)
    team2_name = Column(String(50), nullable=False)
    kickoff_utc = Column(DateTime(timezone=True), nullable=False)
    result_goals1 = Column(Integer, nullable=True)
    result_goals2 = Column(Integer, nullable=True)
    is_finished = Column(Boolean, default=False, nullable=False, server_default="false")
    is_visible = Column(Boolean, default=False, nullable=False, server_default="false")
    finished_at = Column(DateTime(timezone=True), nullable=True)  # set when admin enters result

    phase = relationship("Phase", back_populates="matches")
    predictions = relationship("Prediction", back_populates="match")
    result_logs = relationship("ResultLog", back_populates="match")
    prediction_logs = relationship("PredictionLog", back_populates="match")
    badges = relationship("UserBadge", back_populates="match")

    __table_args__ = (
        Index("ix_matches_kickoff_utc", "kickoff_utc"),
        Index("ix_matches_phase_id", "phase_id"),
    )


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    pred_goals1 = Column(Integer, nullable=False)
    pred_goals2 = Column(Integer, nullable=False)
    is_joker = Column(Boolean, default=False, nullable=False, server_default="false")
    points = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="predictions", foreign_keys=[user_id])
    match = relationship("Match", back_populates="predictions")
    logs = relationship("PredictionLog", back_populates="prediction")

    __table_args__ = (
        UniqueConstraint("user_id", "match_id", name="uq_prediction_user_match"),
        Index("ix_predictions_user_id", "user_id"),
        Index("ix_predictions_match_id", "match_id"),
    )


class ResultLog(Base):
    __tablename__ = "result_log"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    old_goals1 = Column(Integer, nullable=True)
    old_goals2 = Column(Integer, nullable=True)
    new_goals1 = Column(Integer, nullable=True)
    new_goals2 = Column(Integer, nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    match = relationship("Match", back_populates="result_logs")
    changed_by_user = relationship("User", back_populates="result_changes")


class PredictionLog(Base):
    """Audit trail for every prediction create/edit."""
    __tablename__ = "prediction_log"

    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey("predictions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    old_goals1 = Column(Integer, nullable=True)
    old_goals2 = Column(Integer, nullable=True)
    new_goals1 = Column(Integer, nullable=False)
    new_goals2 = Column(Integer, nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    prediction = relationship("Prediction", back_populates="logs")
    match = relationship("Match", back_populates="prediction_logs")
    user = relationship("User", foreign_keys=[user_id])
    changed_by_user = relationship(
        "User", back_populates="prediction_changes_made", foreign_keys=[changed_by]
    )


class UserBadge(Base):
    __tablename__ = "user_badges"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    badge_code = Column(String(50), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)
    # NULL = personal badge (prophet, hot_streak, joker_*, iron_man)
    # set  = league-specific badge (lone_wolf, sheep, comeback_king, group_stage_guru)
    league_id = Column(Integer, ForeignKey("leagues.id"), nullable=True)
    awarded_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")

    user = relationship("User", back_populates="badges")
    match = relationship("Match", back_populates="badges")
    league = relationship("League")

    __table_args__ = (
        UniqueConstraint("user_id", "badge_code", "match_id", "league_id", name="uq_user_badge"),
    )
