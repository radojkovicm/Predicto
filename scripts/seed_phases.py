#!/usr/bin/env python
"""Seed the 8 WC 2026 phases. Safe to run multiple times (idempotent)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models.models import Phase

PHASES = [
    (1, "Group Stage 1",       True),
    (2, "Group Stage 2",       True),
    (3, "Group Stage 3",       True),
    (4, "Round of 32",         True),
    (5, "Round of 16",         True),
    (6, "Quarter-finals",      True),
    (7, "Semi-finals",         True),
    (8, "Final / 3rd place",   True),
]


def seed():
    db = SessionLocal()
    try:
        for order_index, name, joker_allowed in PHASES:
            existing = db.query(Phase).filter(Phase.order_index == order_index).first()
            if not existing:
                db.add(Phase(name=name, order_index=order_index, joker_allowed=joker_allowed))
                print(f"  Created phase: {name}")
            else:
                print(f"  Phase already exists: {existing.name}")
        db.commit()
        print("Phases seeded successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
