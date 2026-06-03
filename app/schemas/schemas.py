from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class PredictionCreate(BaseModel):
    match_id: int
    pred_goals1: int = Field(..., ge=0, le=99)
    pred_goals2: int = Field(..., ge=0, le=99)
    is_joker: bool = False


class MatchCreate(BaseModel):
    phase_id: int
    team1_code: str = Field(..., min_length=2, max_length=5)
    team1_name: str = Field(..., min_length=1, max_length=50)
    team2_code: str = Field(..., min_length=2, max_length=5)
    team2_name: str = Field(..., min_length=1, max_length=50)
    kickoff_utc: datetime

    @field_validator("team1_code", "team2_code")
    @classmethod
    def lower_code(cls, v: str) -> str:
        return v.lower().strip()


class MatchEdit(MatchCreate):
    pass


class ResultEntry(BaseModel):
    goals1: int = Field(..., ge=0, le=99)
    goals2: int = Field(..., ge=0, le=99)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6)


class PasswordReset(BaseModel):
    new_password: str = Field(..., min_length=6)


class ReminderUser(BaseModel):
    user_id: int
    username: str
    missing_matches: list[int]
