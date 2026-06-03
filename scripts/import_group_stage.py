#!/usr/bin/env python
"""Import Group Stage 1/2/3 matches from embedded CSV.
Kickoff times in CSV are Europe/Ljubljana — converted to UTC for storage.
Safe to re-run: skips matches that already exist (same phase + teams + kickoff).
"""
import csv
import io
import os
import sys

import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from app.db import SessionLocal
from app.models.models import Match, Phase

TZ_LJU = pytz.timezone("Europe/Ljubljana")

CSV_DATA = """\
phase,team1_code,team1_name,team2_code,team2_name,kickoff_ljubljana,group
Group Stage 1,mx,Mexico,za,South Africa,2026-06-11 21:00,A
Group Stage 1,kr,South Korea,tbd,UEFA Play-off D,2026-06-12 03:00,A
Group Stage 1,ca,Canada,tbd,UEFA Play-off A,2026-06-12 21:00,B
Group Stage 1,qa,Qatar,ch,Switzerland,2026-06-13 21:00,B
Group Stage 1,br,Brazil,ma,Morocco,2026-06-14 00:00,C
Group Stage 1,ht,Haiti,gb-sct,Scotland,2026-06-14 03:00,C
Group Stage 1,us,USA,py,Paraguay,2026-06-13 03:00,D
Group Stage 1,au,Australia,tbd,UEFA Play-off C,2026-06-13 06:00,D
Group Stage 1,de,Germany,cw,Curacao,2026-06-14 19:00,E
Group Stage 1,ci,Cote d'Ivoire,ec,Ecuador,2026-06-15 01:00,E
Group Stage 1,nl,Netherlands,jp,Japan,2026-06-14 22:00,F
Group Stage 1,tbd,UEFA Play-off B,tn,Tunisia,2026-06-15 03:00,F
Group Stage 1,ir,Iran,nz,New Zealand,2026-06-16 03:00,G
Group Stage 1,be,Belgium,eg,Egypt,2026-06-15 21:00,G
Group Stage 1,es,Spain,cv,Cape Verde,2026-06-15 18:00,H
Group Stage 1,sa,Saudi Arabia,uy,Uruguay,2026-06-16 00:00,H
Group Stage 1,fr,France,sn,Senegal,2026-06-16 21:00,I
Group Stage 1,tbd,FIFA Play-off 2,no,Norway,2026-06-17 00:00,I
Group Stage 1,ar,Argentina,dz,Algeria,2026-06-17 03:00,J
Group Stage 1,at,Austria,jo,Jordan,2026-06-17 06:00,J
Group Stage 1,pt,Portugal,tbd,FIFA Play-off 1,2026-06-17 19:00,K
Group Stage 1,uz,Uzbekistan,co,Colombia,2026-06-18 04:00,K
Group Stage 1,gb-eng,England,hr,Croatia,2026-06-17 22:00,L
Group Stage 1,gh,Ghana,pa,Panama,2026-06-18 01:00,L
Group Stage 2,tbd,UEFA Play-off D,za,South Africa,2026-06-18 18:00,A
Group Stage 2,mx,Mexico,kr,South Korea,2026-06-19 03:00,A
Group Stage 2,ch,Switzerland,tbd,UEFA Play-off A,2026-06-18 21:00,B
Group Stage 2,ca,Canada,qa,Qatar,2026-06-19 03:00,B
Group Stage 2,gb-sct,Scotland,ma,Morocco,2026-06-20 00:00,C
Group Stage 2,br,Brazil,ht,Haiti,2026-06-20 03:00,C
Group Stage 2,us,USA,au,Australia,2026-06-19 21:00,D
Group Stage 2,tbd,UEFA Play-off C,py,Paraguay,2026-06-20 03:00,D
Group Stage 2,de,Germany,ci,Cote d'Ivoire,2026-06-20 22:00,E
Group Stage 2,ec,Ecuador,cw,Curacao,2026-06-21 02:00,E
Group Stage 2,nl,Netherlands,tbd,UEFA Play-off B,2026-06-20 19:00,F
Group Stage 2,tn,Tunisia,jp,Japan,2026-06-21 06:00,F
Group Stage 2,be,Belgium,ir,Iran,2026-06-21 21:00,G
Group Stage 2,nz,New Zealand,eg,Egypt,2026-06-22 03:00,G
Group Stage 2,es,Spain,sa,Saudi Arabia,2026-06-21 18:00,H
Group Stage 2,uy,Uruguay,cv,Cape Verde,2026-06-22 00:00,H
Group Stage 2,fr,France,tbd,FIFA Play-off 2,2026-06-22 23:00,I
Group Stage 2,no,Norway,sn,Senegal,2026-06-23 02:00,I
Group Stage 2,ar,Argentina,at,Austria,2026-06-22 19:00,J
Group Stage 2,jo,Jordan,dz,Algeria,2026-06-23 05:00,J
Group Stage 2,pt,Portugal,uz,Uzbekistan,2026-06-23 19:00,K
Group Stage 2,co,Colombia,tbd,FIFA Play-off 1,2026-06-24 04:00,K
Group Stage 2,gb-eng,England,gh,Ghana,2026-06-23 22:00,L
Group Stage 2,pa,Panama,hr,Croatia,2026-06-24 01:00,L
Group Stage 3,tbd,UEFA Play-off D,mx,Mexico,2026-06-25 03:00,A
Group Stage 3,za,South Africa,kr,South Korea,2026-06-25 03:00,A
Group Stage 3,ch,Switzerland,ca,Canada,2026-06-25 03:00,B
Group Stage 3,tbd,UEFA Play-off A,qa,Qatar,2026-06-24 21:00,B
Group Stage 3,gb-sct,Scotland,br,Brazil,2026-06-25 00:00,C
Group Stage 3,ma,Morocco,ht,Haiti,2026-06-25 00:00,C
Group Stage 3,tbd,UEFA Play-off C,us,USA,2026-06-26 04:00,D
Group Stage 3,py,Paraguay,au,Australia,2026-06-26 04:00,D
Group Stage 3,ec,Ecuador,de,Germany,2026-06-25 22:00,E
Group Stage 3,cw,Curacao,ci,Cote d'Ivoire,2026-06-25 22:00,E
Group Stage 3,jp,Japan,tbd,UEFA Play-off B,2026-06-26 01:00,F
Group Stage 3,tn,Tunisia,nl,Netherlands,2026-06-26 01:00,F
Group Stage 3,eg,Egypt,ir,Iran,2026-06-27 05:00,G
Group Stage 3,nz,New Zealand,be,Belgium,2026-06-27 05:00,G
Group Stage 3,cv,Cape Verde,sa,Saudi Arabia,2026-06-27 02:00,H
Group Stage 3,uy,Uruguay,es,Spain,2026-06-27 02:00,H
Group Stage 3,no,Norway,fr,France,2026-06-26 21:00,I
Group Stage 3,sn,Senegal,tbd,FIFA Play-off 2,2026-06-26 21:00,I
Group Stage 3,dz,Algeria,at,Austria,2026-06-28 04:00,J
Group Stage 3,jo,Jordan,ar,Argentina,2026-06-28 04:00,J
Group Stage 3,co,Colombia,pt,Portugal,2026-06-28 01:00,K
Group Stage 3,tbd,FIFA Play-off 1,uz,Uzbekistan,2026-06-28 01:00,K
Group Stage 3,pa,Panama,gb-eng,England,2026-06-27 23:00,L
Group Stage 3,hr,Croatia,gh,Ghana,2026-06-27 23:00,L
"""


def lju_to_utc(s: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM' Ljubljana time and return UTC-aware datetime."""
    naive = datetime.strptime(s.strip(), "%Y-%m-%d %H:%M")
    return TZ_LJU.localize(naive).astimezone(pytz.utc)


def main():
    db = SessionLocal()
    try:
        phases = {p.name: p.id for p in db.query(Phase).all()}
        if not phases:
            print("No phases found — run scripts/seed_phases.py first.")
            sys.exit(1)

        reader = csv.DictReader(io.StringIO(CSV_DATA.strip()))
        imported = skipped = 0

        for row in reader:
            phase_id = phases.get(row["phase"])
            if not phase_id:
                print(f"  SKIP (unknown phase): {row['phase']}")
                skipped += 1
                continue

            kickoff_utc = lju_to_utc(row["kickoff_ljubljana"])

            # Idempotency check
            exists = (
                db.query(Match)
                .filter(
                    Match.phase_id == phase_id,
                    Match.team1_code == row["team1_code"],
                    Match.team2_code == row["team2_code"],
                    Match.kickoff_utc == kickoff_utc,
                )
                .first()
            )
            if exists:
                skipped += 1
                continue

            db.add(
                Match(
                    phase_id=phase_id,
                    team1_code=row["team1_code"],
                    team1_name=row["team1_name"],
                    team2_code=row["team2_code"],
                    team2_name=row["team2_name"],
                    kickoff_utc=kickoff_utc,
                )
            )
            imported += 1
            print(f"  + {row['phase']} | Grp {row['group']} | "
                  f"{row['team1_name']} vs {row['team2_name']} "
                  f"({row['kickoff_ljubljana']} LJU)")

        db.commit()
        print(f"\nDone: {imported} imported, {skipped} skipped.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
