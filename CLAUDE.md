# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the development server (port 5001)
python app.py

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest
pytest tests/test_specific.py::test_name   # single test
```

## Architecture

Spendly is a Flask + SQLite expense tracker. The project is structured as a teaching scaffold — many routes exist as stubs that students fill in step by step.

**Entry point:** `app.py` — all routes defined here, runs on port 5001 with debug mode.

**Database:** `database/db.py` is a stub. Students implement `get_db()` (SQLite connection with row_factory + foreign keys), `init_db()` (CREATE TABLE IF NOT EXISTS), and `seed_db()` (sample data). No ORM — raw SQLite.

**Templates:** Jinja2. All pages extend `templates/base.html`, which provides the navbar, footer, and loads `static/css/style.css` and `static/js/main.js`. Page-specific scripts go in `{% block scripts %}`.

**Styling:** Single stylesheet at `static/css/style.css`. All design uses CSS custom properties — never hardcode colors or fonts. The full token set:
- Colors: `--ink`, `--ink-soft`, `--ink-muted`, `--ink-faint`, `--paper`, `--paper-warm`, `--paper-card`, `--accent` (dark green), `--accent-light`, `--accent-2` (amber), `--accent-2-light`, `--danger`, `--danger-light`, `--border`, `--border-soft`
- Typography: `--font-display` (DM Serif Display, serif), `--font-body` (DM Sans, sans-serif)
- Layout: `--max-width` (1200px), `--auth-width` (440px)
- Radii: `--radius-sm`, `--radius-md`, `--radius-lg`

**Stub routes** (not yet implemented — return placeholder strings):
- `/logout`, `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`

**Implemented routes:** `/` (landing), `/register`, `/login`, `/terms`, `/privacy`
