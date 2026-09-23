#!/usr/bin/env python
"""Seed the 8 default phases for a competition. Safe to run multiple times (idempotent).

Usage: python scripts/seed_phases.py --competition-id <id>
"""
import argparse
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models.models import Competition, Phase

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

GROUP_STAGE_ORDER_INDICES = {1, 2, 3}


def seed(competition_id: int):
    db = SessionLocal()
    try:
        competition = db.query(Competition).filter(Competition.id == competition_id).first()
        if not competition:
            print(f"Competition with id {competition_id} not found.")
            sys.exit(1)

        for order_index, name, joker_allowed in PHASES:
            existing = (
                db.query(Phase)
                .filter(Phase.order_index == order_index, Phase.competition_id == competition.id)
                .first()
            )
            if not existing:
                db.add(Phase(
                    name=name,
                    order_index=order_index,
                    joker_allowed=joker_allowed,
                    competition_id=competition.id,
                    is_group_stage=order_index in GROUP_STAGE_ORDER_INDICES,
                    point_multiplier=1.00,
                ))
                print(f"  Created phase: {name}")
            else:
                print(f"  Phase already exists: {existing.name}")
        db.commit()
        print(f"Phases seeded successfully for competition '{competition.name}'.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition-id", type=int, required=True, help="ID of the competition to seed phases for")
    args = parser.parse_args()
    seed(args.competition_id)
