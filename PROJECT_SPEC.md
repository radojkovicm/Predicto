# PROJECT SPEC — World Cup 2026 Prediction Game

> This is the complete build specification. UI and all user-facing text in **English**. Code comments in English.

---

## 1. Goal

A self-hosted web app for an **internal office** World Cup 2026 score-prediction game. **No money involved — for fun only.** Users predict exact match scores; points are awarded by a fixed scoring formula. An admin creates users, matches, and enters results manually. The app shows a leaderboard, per-match prediction statistics after lock, achievement badges, and supports dark mode + mobile.

This is a fresh build inspired by an older app — **do not copy any external code**. Only the scoring rules below are reused.

---

## 2. Tech Stack (mandatory)

- **Backend:** Python 3.11+, FastAPI
- **DB:** PostgreSQL (SQLAlchemy 2.x ORM + Alembic migrations)
- **Templating:** Jinja2 (server-rendered, no SPA framework)
- **Auth:** session cookie (HttpOnly, Secure, SameSite=Lax) + bcrypt password hashing
- **Validation:** Pydantic v2
- **Frontend:** Jinja2 + minimal vanilla JS + plain CSS (responsive, dark mode). No heavy frameworks.
- **Deploy target:** Docker container on Coolify/Traefik (HTTPS via Let's Encrypt). Timezone display **Europe/Ljubljana**, all timestamps stored in **UTC**.

---

## 3. Scoring Rules (EXACT — this is the heart of the app, must be 100% correct)

For each match, points are **summed** (max 25 from base):

```
outcome(a, b) = HOME if a > b, DRAW if a == b, AWAY if a < b

points = 0
if outcome(pred1, pred2) == outcome(res1, res2):  points += 10   # correct tip
if (pred1 - pred2) == (res1 - res2):              points += 7    # correct goal difference
if pred1 == res1:                                 points += 4    # correct goals team 1
if pred2 == res2:                                 points += 4    # correct goals team 2
```

**Joker** (applied on top of base points for that match):
```
if prediction.is_joker:
    if outcome(pred) == outcome(res):  points += 8    # joker hit
    else:                              points -= 5    # joker miss
```

**Critical rules:**
- Result used = **score at end of extra time** (penalties are NOT counted). Admin enters the final score that already reflects extra time.
- **8 jokers total per user**, exactly **1 per phase** (3 group phases + 5 playoff phases). Enforce max 1 joker per (user, phase) at save time.
- A perfect base prediction = 25 points (10 + 7 + 4 + 4). With joker hit = 33.

---

## 4. Lock Rule

- A prediction can be created/edited **only while** `now_utc < match.kickoff_utc - 15 minutes`.
- Once locked, the user can no longer change it.
- Other users' predictions for a match become **visible only after that match is locked**.
- All lock math is done in **UTC**.

---

## 5. Data Model (PostgreSQL via SQLAlchemy)

### `users`
- `id` PK
- `username` unique, not null
- `password_hash` (bcrypt)
- `is_admin` bool, default false
- `created_at` timestamptz default now()

### `phases`
- `id` PK
- `name` (e.g. "Group Stage 1", "Group Stage 2", "Group Stage 3", "Round of 32", "Round of 16", "Quarter-finals", "Semi-finals", "Final / 3rd place")
- `order_index` int (1..8)
- `joker_allowed` bool default true

Seed 8 phases on first run.

### `matches`
- `id` PK
- `phase_id` FK -> phases
- `team1_code` (ISO-ish 2-letter for flag CSS, e.g. "mx"), `team1_name` (e.g. "MEX")
- `team2_code`, `team2_name`
- `kickoff_utc` timestamptz, not null
- `result_goals1` int nullable, `result_goals2` int nullable
- `is_finished` bool default false
- Indexes: `kickoff_utc`, `phase_id`

### `predictions`
- `id` PK
- `user_id` FK, `match_id` FK
- `pred_goals1` int (0–99), `pred_goals2` int (0–99)
- `is_joker` bool default false
- `points` int nullable (computed after result entered)
- `created_at`, `updated_at` timestamptz
- **UNIQUE(user_id, match_id)**
- Indexes: `user_id`, `match_id`

### `result_log` (simple change log)
- `id` PK
- `match_id` FK
- `old_goals1`, `old_goals2`, `new_goals1`, `new_goals2` (nullable ints)
- `changed_by` FK -> users
- `changed_at` timestamptz default now()

### `user_badges`
- `id` PK
- `user_id` FK
- `badge_code` (string, see badge list)
- `match_id` FK nullable (badge context, where applicable)
- `awarded_at` timestamptz
- UNIQUE(user_id, badge_code, match_id) to avoid duplicates

---

## 6. Services (business logic layer)

Keep routes thin. All logic in `app/services/`:

- **`scoring_service.py`** — `compute_points(pred, result, is_joker) -> int`. Pure function, fully unit-tested.
- **`prediction_service.py`** — create/update with lock check + joker-per-phase check + validation.
- **`ranking_service.py`** — leaderboard with tie-break (see §7). Excludes nobody (no payment concept).
- **`lock_service.py`** — `is_locked(match) -> bool`, `lock_threshold(match)`.
- **`result_service.py`** — admin enters/edits result → writes `result_log` → recomputes `points` for ALL predictions on that match → triggers badge evaluation.
- **`stats_service.py`** — per-match prediction distribution (after lock): % HOME/DRAW/AWAY, most common exact score, count correct/wrong after result.
- **`badge_service.py`** — evaluates and awards badges after each result entry (see §8).

---

## 7. Leaderboard + Tie-break

Rank by, in order:
1. Total points (sum of `predictions.points`) — DESC
2. Number of correct tips (predictions where outcome matched) — DESC
3. Number of correct exact scores (pred1==res1 AND pred2==res2) — DESC
4. Earliest timestamp of last prediction (rewards committing early) — ASC

Leaderboard must compute efficiently with a single aggregate query where possible (SUM/COUNT grouped by user). ~20–50 users, ~104 matches — trivial load, no caching needed.

---

## 8. Badges (all English, evaluate after each result entry)

| `badge_code` | Display name | Condition |
|---|---|---|
| `prophet` | **Prophet** | Earned a perfect base 25 on a match (correct exact score) |
| `hot_streak` | **Hot Streak** | 3 consecutive matches (by kickoff order, finished) each with ≥10 points |
| `joker_master` | **Joker Master** | A joker prediction that hit (+8 applied) |
| `joker_victim` | **Joker Victim** | A joker prediction that missed (−5 applied) — fun "badge of shame" |
| `lone_wolf` | **Lone Wolf** | Only user to get the correct tip on a match where the large majority got it wrong (threshold: ≥70% of participants wrong AND user is the sole correct-tip, or among ≤1 correct) |
| `sheep` | **Sheep** | Predicted the same outcome as the majority, and that majority got it wrong |
| `comeback_king` | **Comeback King** | Jumped 5+ positions on the leaderboard within a single day's result batch |
| `iron_man` | **Iron Man** | Submitted a prediction for every match in a phase (none missed) |
| `group_stage_guru` | **Group Stage Guru** | Highest total points across the 3 group phases (awarded once group stage complete) |

Badges display on the user's profile and as small icons next to their name on the leaderboard. Awarding is idempotent (UNIQUE constraint prevents duplicates). Some badges are per-match (`prophet`, `joker_*`, `lone_wolf`, `sheep`), some are aggregate (`hot_streak`, `comeback_king`, `iron_man`, `group_stage_guru`).

---

## 9. Per-match Statistics (after lock / after result)

On a match detail page, **after the match is locked**, show:
- Distribution: % who predicted HOME win / DRAW / AWAY win
- Most common exact score predicted
- List of all users' predictions (visible only post-lock)

**After result entered**, also show:
- "Only X of Y players got this right!" (count of correct tips) — the misses/hits highlight
- Praise line for those who nailed the exact score (lists the Prophets for that match)

---

## 10. Routes / Pages

**Public:**
- `GET /login`, `POST /login` (rate-limited: 5 attempts → temporary lockout ~5 min, per username+IP)
- `POST /logout`

**User (auth required):**
- `GET /` → redirect to match list
- `GET /matches?phase_id=` → match list grouped by phase (Group / Playoff tabs), shows kickoff in Europe/Ljubljana, lock status icon, user's own prediction, points if finished
- `GET /matches/{id}` → match detail + prediction form (if not locked) + stats (if locked)
- `POST /predictions` → create/update (validated, lock-checked, joker-checked)
- `GET /ranking` → leaderboard with tie-break + badge icons
- `GET /profile` / `GET /profile/{user_id}` → points, badges, history
- `GET /info` → rules page (scoring explained, in English)

**Admin (is_admin required, behind `require_admin` dependency):**
- `GET/POST /admin/users` → create users (set username + initial password), reset password
- `GET/POST /admin/matches` → create/edit matches (teams, codes, kickoff, phase)
- `POST /admin/matches/{id}/result` → enter/edit result → logs change, recomputes points, re-evaluates badges
- `GET /admin/log` → view result change log

**Integration:**
- `GET /api/reminder-data` → protected by a static token (env var); returns JSON of users who haven't predicted today's upcoming matches. Consumed by external **n8n** for reminders. Keep the app simple — n8n does the actual messaging.

---

## 11. Security

- Passwords: **bcrypt** (passlib).
- Sessions: signed, HttpOnly + Secure + SameSite=Lax cookies (use `itsdangerous` or starlette session middleware with a strong secret from env).
- **Rate limiting** on login (e.g. `slowapi`): 5 failed attempts → temp lockout. Brute-force protection is mandatory for a publicly reachable login.
- All admin routes behind `require_admin` dependency.
- Pydantic validation on every input. Goals constrained to int 0–99.
- Parameterized queries only (ORM) — no string-built SQL.
- Hide server version headers.
- All secrets in `.env` (never committed). Provide `.env.example` with dummy values.

---

## 12. Folder Structure

```
wc2026/
├── app/
│   ├── main.py                 # FastAPI app, middleware, router mounting
│   ├── db.py                   # engine, session
│   ├── models/                 # SQLAlchemy models (one file or split)
│   ├── schemas/                # Pydantic schemas
│   ├── services/
│   │   ├── scoring_service.py
│   │   ├── prediction_service.py
│   │   ├── ranking_service.py
│   │   ├── lock_service.py
│   │   ├── result_service.py
│   │   ├── stats_service.py
│   │   └── badge_service.py
│   ├── routes/
│   │   ├── auth.py
│   │   ├── matches.py
│   │   ├── predictions.py
│   │   ├── ranking.py
│   │   ├── profile.py
│   │   ├── admin.py
│   │   └── integration.py
│   ├── auth/                   # session helpers, password hashing, deps
│   ├── templates/              # Jinja2: base.html, login, matches, match_detail,
│   │                           #         ranking, profile, info, admin/*
│   └── static/                 # css (incl. dark mode), minimal js, flag css
├── alembic/                    # migrations
├── config/
│   ├── config.py               # settings via pydantic-settings, reads .env
│   └── .env.example
├── scripts/
│   ├── seed_phases.py          # seed 8 phases
│   ├── create_admin.py         # CLI to create first admin
│   └── backup.sh               # pg_dump backup (for VPS cron)
├── tests/
│   ├── unit/                   # scoring_service tests (critical), tie-break, badges
│   └── integration/
├── Dockerfile
├── docker-compose.yml          # app + postgres (for local/coolify reference)
├── requirements.txt
└── README.md
```

---

## 13. Backup (VPS)

Provide `scripts/backup.sh` doing a timestamped `pg_dump`, plus README instructions to register it as a daily cron job on the VPS. Keep last N dumps, rotate older ones.

---

## 14. Tests (mandatory for scoring)

Unit tests must cover, at minimum:
- Scoring: exact hit (25), correct tip only (10), correct GD only (7), correct goals team1/team2 (4 each), draw cases (0:0, 2:2), wrong everything (0).
- Joker: hit (+8 on top), miss (−5), and that −5 can make a match negative.
- Joker-per-phase enforcement (cannot use 2 jokers in one phase).
- Lock: cannot create/edit within 15 min of kickoff; can before.
- Tie-break ordering correctness.
- Badge awarding idempotency.

Edge cases: empty/missing prediction, goals at bounds (0 and 99), extra-time-only result entry.

---

## 15. Build Order (suggested)

1. Project scaffold, config, `requirements.txt`, db setup, models, Alembic init migration.
2. `scoring_service.py` + full unit tests (get this green first).
3. Auth (session, bcrypt, login rate-limit, `create_admin` script, seed phases).
4. User flow: match list → match detail → prediction (lock + joker checks) → ranking (tie-break).
5. Admin: users, matches, result entry (with `result_log` + point recompute).
6. Badges + per-match stats + profile pages.
7. Templates polish: responsive + dark mode + flag CSS. Info/rules page.
8. n8n integration endpoint.
9. Dockerfile + docker-compose + README + backup script.

---

## 16. Notes / Deferred (v2 — do NOT build now)

- Knockout bracket prediction (advance-team bonus points) — explicitly deferred to v2.
- No payment / participation tracking (game is for fun, no money).
- No in-app chat, no leaderboard animations, no daily-roundup screen.

---

## 17. Deliverable Expectations

- Clean, documented code (docstrings on services, comments only where logic is non-obvious).
- `README.md`: local setup, env vars, running migrations, creating admin, seeding phases, Docker deploy notes for Coolify, registering the backup cron.
- App must run end-to-end: admin can create a user + match, user can predict, admin enters result, points compute, leaderboard updates, badges award, stats show.
