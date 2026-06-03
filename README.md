# WC 2026 Predicto

Office World Cup 2026 score-prediction game. Self-hosted, no money involved — for fun only.

---

## Moving from SQLite (local) to PostgreSQL (VPS)

If you developed locally with SQLite and are now deploying to production:

### Option A — Fresh start on VPS (recommended)
Everything stays in the code. Just run setup on the VPS from scratch.

### Option B — Clean local test data first, then deploy
```bash
# On local machine — resets test users/results, keeps all matches
python scripts/reset_test_data.py

# Then copy files to VPS and follow VPS setup below
```

---

## VPS Setup (PostgreSQL)

### 1. On the PostgreSQL server
```sql
CREATE USER predicto WITH PASSWORD 'strongpassword';
CREATE DATABASE predicto OWNER predicto;
```

### 2. Copy project to VPS, then:
```bash
pip install -r requirements.txt
```

### 3. Create `.env` on the VPS
```
DATABASE_URL=postgresql://predicto:strongpassword@localhost:5432/predicto
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
REMINDER_API_TOKEN=<generate: python -c "import secrets; print(secrets.token_hex(16))">
DEBUG=false
```

### 4. Run setup
```bash
alembic upgrade head
python scripts/seed_phases.py
python scripts/import_group_stage.py
python scripts/create_admin.py
```

### 5. Start
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
```

Or with Docker (see Docker section below).

---

## Quick Start (Local — SQLite)

### 1. Prerequisites
- Python 3.11+
- PostgreSQL 14+

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp config/.env.example .env
# Edit .env with your values
```

Required env vars:
| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/dbname` |
| `SECRET_KEY` | Long random string for session signing |
| `REMINDER_API_TOKEN` | Static token for the n8n reminder endpoint |
| `DEBUG` | `true` for local dev (disables HTTPS-only cookies) |

### 4. Run migrations

```bash
alembic upgrade head
```

### 5. Seed phases

```bash
python scripts/seed_phases.py
```

### 6. Create admin user

```bash
python scripts/create_admin.py
```

### 7. Run the app

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000

---

## Running Tests

```bash
pytest tests/unit/ -v
```

The scoring tests are the most critical — they must pass before deploying.

---

## Docker Deploy (Coolify / Traefik)

### 1. Set env vars in Coolify

Configure these in the Coolify environment panel:
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

### 3. Run migrations inside container

```bash
docker compose exec app alembic upgrade head
docker compose exec app python scripts/seed_phases.py
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

## Security Notes

- Passwords hashed with bcrypt
- Session cookies: HttpOnly + SameSite=Lax + Secure (in production)
- IP rate limiting on login: 10 requests/minute per IP (slowapi)
- Account lockout: 30 minutes after 10 failed login attempts
- Admin can unlock accounts manually at `/admin/users`
- Prediction audit log at `/admin/prediction-log` — every prediction change is recorded
- Result audit log at `/admin/log`
- All DB queries via ORM (no string-built SQL)

---

## Folder Structure

```
app/
  main.py          FastAPI app + middleware
  db.py            SQLAlchemy engine + session
  models/          SQLAlchemy models
  schemas/         Pydantic v2 schemas
  auth/            Password hashing, session helpers, deps
  services/        Business logic (scoring, predictions, ranking, badges, stats, results)
  routes/          Route handlers
  templates/       Jinja2 templates
  static/          CSS + JS
alembic/           Migrations
config/            Settings via pydantic-settings
scripts/           seed_phases, create_admin, backup
tests/unit/        Scoring, lock, ranking, badge unit tests
```
