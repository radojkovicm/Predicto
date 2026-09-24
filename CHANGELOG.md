# Changelog

## v1.0.0 — Final release (2026-09-24)

The first and final stable release of Predicto.

### Features
- Multi-competition support, each competition with its own phases and scoring rules
- Exact-score predictions with a joker per phase and per-phase point multipliers
- Leagues with separate leaderboards, invite links and archiving
- Prediction lock before kickoff, then post-lock stats and everyone's tips
- Achievement badges, personal stats and prediction history
- Admin panel: competitions, phases, matches, results, users, leagues, audit logs, Excel import
- CSRF protection, bcrypt passwords, login rate limiting, account lockout, soft-deleted users
- n8n-friendly reminder API
- Vercel deployment with a zero-config SQLite demo mode, or Docker with PostgreSQL

### Interface
- Modern, mobile-first design with dark and light themes
- Bottom tab bar on phones
- Big +/− score steppers: a tip takes two taps
- "N matches waiting for your tip" reminder banner
- Kickoff countdown, matches grouped by day ("Today", "Tomorrow")
- Leaderboard podium and player avatars
- One-tap demo accounts on the login page
