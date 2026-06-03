#!/usr/bin/env python
"""Reset test data — keeps all matches intact, wipes everything else.

Deletes: users (except admins you choose to keep), predictions,
         results, badges, leagues, prediction_log, result_log, user_leagues.
Resets:  match results (is_finished, goals, finished_at) back to unplayed.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models.models import (
    League, Match, Prediction, PredictionLog, ResultLog,
    User, UserBadge, UserLeague,
)


def confirm(msg: str) -> bool:
    answer = input(f"{msg} [y/N]: ").strip().lower()
    return answer == "y"


def main():
    print("=" * 55)
    print("  Predicto — Reset Test Data")
    print("=" * 55)
    print()

    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.username).all()
        print("Current users:")
        for u in users:
            print(f"  [{u.id}] {u.username} {'(admin)' if u.is_admin else ''}")

        keep_input = input(
            "\nEnter user IDs to KEEP (comma-separated), or press Enter to delete all: "
        ).strip()

        keep_ids = set()
        if keep_input:
            keep_ids = {int(x.strip()) for x in keep_input.split(",") if x.strip().isdigit()}

        delete_users = [u for u in users if u.id not in keep_ids]
        print()
        if delete_users:
            print(f"Will DELETE {len(delete_users)} user(s): {[u.username for u in delete_users]}")
        else:
            print("No users will be deleted.")

        match_count = db.query(Match).filter(Match.is_finished == True).count()
        print(f"Will RESET {match_count} finished match result(s).")
        print("Will DELETE all: predictions, badges, leagues, logs.")
        print()

        if not confirm("Proceed with reset?"):
            print("Aborted.")
            return

        # Delete in FK-safe order
        db.query(PredictionLog).delete(synchronize_session=False)
        db.query(ResultLog).delete(synchronize_session=False)
        db.query(UserBadge).delete(synchronize_session=False)
        db.query(Prediction).delete(synchronize_session=False)
        db.query(UserLeague).delete(synchronize_session=False)
        db.query(League).delete(synchronize_session=False)

        for u in delete_users:
            db.delete(u)

        # Reset match results
        db.query(Match).update(
            {
                "result_goals1": None,
                "result_goals2": None,
                "is_finished": False,
                "finished_at": None,
            },
            synchronize_session=False,
        )

        db.commit()
        print()
        print("Done! Kept matches intact. Database is ready for production.")
        remaining = db.query(User).count()
        print(f"Remaining users: {remaining}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
