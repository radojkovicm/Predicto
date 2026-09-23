# ⚽ Predicto — Score Prediction Game

A self-hosted score-prediction pool for **any football competition** — a World Cup, a Champions League season, your office's Sunday league, whatever. Admins spin up a competition with its own scoring rules and phases, users predict exact match scores, and a leaderboard tracks the standings per league. **No money involved — for fun only.**

Built with **FastAPI + SQLAlchemy + Jinja2** — server-rendered, no SPA framework, dark mode by default.

[**Live demo →**](#) *(add your deployed URL here once you deploy — see [Deploy to Vercel](#deploy-to-vercel) below)*

---

## Screenshots

| Matches | Leaderboard |
|---|---|
| ![Matches list](docs/screenshots/matches.png) | ![Leaderboard](docs/screenshots/ranking.png) |

| Match detail & stats | Admin panel |
|---|---|
| ![Match detail](docs/screenshots/match_detail.png) | ![Admin panel](docs/screenshots/admin.png) |

---

## Features

- **Multi-competition** — run any number of competitions (past, active, or archived), each with its own name, phases, and scoring configuration
- **Configurable scoring per competition** — points for correct tip / goal difference / exact score, joker bonus/penalty, and a per-phase point multiplier are all admin-editable, not hardcoded
- **Exact-score predictions** — points awarded for correct tip (1X2), correct goal difference, and exact goals per team
- **Joker** — one per phase, doubles down on a prediction for bonus points or a penalty
- **Leagues** — group players into separate leaderboards (e.g. per office/team/friend group), with invite links and archiving once a competition ends
- **Prediction lock** — configurable minutes-before-kickoff cutoff, then predictions are frozen
- **Post-lock stats** — see the outcome distribution and everyone's predictions once a match locks
- **Achievement badges**, personal stats, and per-match prediction history
- **Admin panel** — create/edit competitions, phases and matches, enter results, manage users and leagues, audit logs, soft-delete users while preserving history
- **Excel import** for bulk-loading a competition's fixture list
- **Dark mode** by default, mobile-friendly
- **n8n-friendly reminder API** for nudging users who haven't predicted yet

---

## Tech Stack

- **Backend:** Python 3.11+, FastAPI
- **DB:** PostgreSQL in production (SQLite for local dev), SQLAlchemy 2.x ORM + Alembic migrations
- **Templating:** Jinja2, server-rendered — vanilla JS + plain CSS on top
- **Auth:** session cookies (HttpOnly, Secure, SameSite=Lax) + bcrypt password hashing, CSRF-protected forms
- **Validation:** Pydantic v2

---

## Quick Start (Local)

### 1. Prerequisites
- Python 3.11+
- PostgreSQL 14+ (or just use SQLite for local dev — see below)

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

| Variable | Description |
|---|---|
| `DATABASE_URL` | `sqlite:///./predicto.db` for local dev, or `postgresql://user:pass@host:5432/dbname` |
| `SECRET_KEY` | Long random string for session signing |
| `REMINDER_API_TOKEN` | Static token for the n8n reminder endpoint |
| `DEBUG` | `true` for local dev (disables HTTPS-only cookies) |

### 4. Run migrations and create an admin

```bash
alembic upgrade head
python scripts/create_admin.py
```

### 5. Run the app

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000, log in as the admin, and create your first competition at `/admin/competitions` — add phases, then matches (one by one or via the Excel importer), and you're running.

`scripts/seed_phases.py` and `scripts/import_group_stage.py` are optional convenience scripts that preload a sample World Cup 2026-style fixture list, useful for trying the app out — they're not required for a real competition, everything they do can also be done from the admin panel.

---

## Running Tests

```bash
pytest tests/unit/ -v
```

The scoring tests are the most critical — they must pass before deploying.

---

## Deploy to Vercel

The repo ships with a `vercel.json` + `api/index.py` entry point, so it deploys as a serverless FastAPI app. Vercel functions have no persistent filesystem, so you need an **external PostgreSQL** database (e.g. [Neon](https://neon.tech) or [Supabase](https://supabase.com) both have a free tier).

### 1. Create a free Postgres database

Grab the connection string (looks like `postgresql://user:pass@host/dbname?sslmode=require`).

### 2. Import the project on Vercel

- [vercel.com/new](https://vercel.com/new) → import this GitHub repo
- Framework preset: **Other**

### 3. Set environment variables

In the Vercel project settings → Environment Variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | your Postgres connection string |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `REMINDER_API_TOKEN` | `python -c "import secrets; print(secrets.token_hex(16))"` |
| `DEBUG` | `false` |

### 4. Run migrations against the remote DB (from your machine)

```bash
export DATABASE_URL="postgresql://...your-neon-url..."
alembic upgrade head
python scripts/create_admin.py
python scripts/seed_phases.py         # optional: sample phases to try the app with
python scripts/import_group_stage.py  # optional: preloads a sample fixture list
```

### 5. Deploy

```bash
vercel --prod
```

**Note:** Vercel's serverless functions are stateless and spin up cold per request, so the in-memory login rate limiter (`slowapi`) resets between invocations — fine for a demo, not a substitute for the VPS/Docker deployment below for a real, higher-traffic pool.

---

## Docker Deploy (VPS / Coolify / Traefik)

For always-on self-hosting with persistent rate limiting, use Docker instead.

### 1. Set env vars in Coolify (or a `.env` next to `docker-compose.yml`)

```
SECRET_KEY=<strong-random-32+-char-string>
REMINDER_API_TOKEN=<random-token>
POSTGRES_PASSWORD=<strong-password>
DEBUG=false
```

### 2. Build & start

```bash
docker compose up -d --build
```

### 3. Run migrations inside the container

```bash
docker compose exec app alembic upgrade head
docker compose exec app python scripts/create_admin.py
```

### 4. Traefik HTTPS

Add these labels to the `app` service in `docker-compose.yml`:

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.predicto.rule=Host(`predicto.yourdomain.com`)"
  - "traefik.http.routers.predicto.entrypoints=websecure"
  - "traefik.http.routers.predicto.tls.certresolver=letsencrypt"
```

---

## Backup (VPS Cron)

```bash
chmod +x scripts/backup.sh

# Add to crontab (runs daily at 03:00):
# crontab -e
0 3 * * * DATABASE_URL="postgresql://..." BACKUP_DIR="/backups/predicto" /path/to/scripts/backup.sh >> /var/log/predicto-backup.log 2>&1
```

Backups are gzip-compressed pg_dumps. Set `KEEP_DAYS` to control rotation (default: 14 days).

---

## n8n Reminder Integration

`GET /api/reminder-data` returns JSON of users who haven't predicted today's upcoming unlocked matches.

**Authentication:** `Authorization: Bearer <REMINDER_API_TOKEN>`

**Response:**
```json
{
  "users": [
    {
      "user_id": 3,
      "username": "john",
      "missing_match_ids": [42, 43]
    }
  ]
}
```

Wire this into an n8n workflow to send Slack/email/SMS reminders.

---

## Scoring Rules

Every competition has its own scoring configuration (editable in the admin panel); the defaults are:

For each match, points are summed (max 25 from base):

```
outcome(a, b) = HOME if a > b, DRAW if a == b, AWAY if a < b

points = 0
if outcome(pred1, pred2) == outcome(res1, res2):  points += 10   # correct tip
if (pred1 - pred2) == (res1 - res2):              points += 7    # correct goal difference
if pred1 == res1:                                 points += 4    # correct goals team 1
if pred2 == res2:                                 points += 4    # correct goals team 2
```

**Joker** (applied on top of base points for that match, one per phase by default):
```
if prediction.is_joker:
    if outcome(pred) == outcome(res):  points += 8    # joker hit
    else:                              points -= 5    # joker miss
```

Each phase can also carry a **point multiplier** (e.g. weight knockout rounds higher than the group stage). Result used = score at end of extra time (penalties are not counted). A prediction can be created/edited only until the configured lock cutoff before kickoff.

---

## Security Notes

- Passwords hashed with bcrypt
- CSRF tokens on all session-authenticated forms
- Session cookies: HttpOnly + SameSite=Lax + Secure (in production)
- IP rate limiting on login: 10 requests/minute per IP (slowapi)
- Account lockout: 30 minutes after 10 failed login attempts
- Admin can unlock accounts manually at `/admin/users`
- Users are soft-deleted (history preserved), never hard-deleted
- Prediction audit log at `/admin/prediction-log` — every prediction change is recorded
- Result audit log at `/admin/log`
- All DB queries via ORM (no string-built SQL)

---

## Folder Structure

```
app/
  main.py          FastAPI app + middleware
  db.py            SQLAlchemy engine + session
  models/          SQLAlchemy models (competitions, phases, matches, leagues, users, ...)
  schemas/         Pydantic v2 schemas
  auth/            Password hashing, session/CSRF helpers, deps
  services/        Business logic (scoring, predictions, ranking, badges, stats, results, import)
  routes/          Route handlers
  templates/       Jinja2 templates
  static/          CSS + JS
api/               Vercel serverless entry point
alembic/           Migrations
config/            Settings via pydantic-settings
scripts/           create_admin, backup, optional sample-data seeders
tests/             Unit + integration tests
```

## License

For personal / community use. No warranty — this is a for-fun project, not a commercial product.
