# Spec: Registration

## Overview
Wire up the registration form so new users can create an account.
The `/register` route currently only handles GET and renders the form.
This step adds POST handling: validate inputs, reject duplicate emails,
hash the password, insert the user row, start a Flask session, and redirect
to the login page with a success indicator. It also sets `app.secret_key`
so Flask sessions work at all.

## Depends on
Step 01 — Database Setup (users table must exist; `get_db()` must be functional).

`get_db()` is expected to return a **sqlite3 connection** (not a cursor).
The implementor must call `.cursor()` on it, then `.commit()` after the INSERT,
and `.close()` when done — or use a `try/finally` block. If Step 01 wraps
`get_db()` differently, defer to that spec; this spec assumes the raw connection pattern.

## Routes
- `GET  /register` — render registration form — public (no change needed)
- `POST /register` — process form submission, create account — public

## Database changes
No database changes. The `users` table from Step 01 already has all
required columns: `id`, `name`, `email`, `password_hash`, `created_at`.

## Templates
- **Modify:** `templates/register.html`
  - Re-populate `name` and `email` fields on validation failure (sticky inputs)
  - The `{% if error %}` block is already present; no structural change needed

## Files to change
- `app.py`
  - Add `app.secret_key` with a hard-coded dev string — see Rules for the required comment format
  - Add `POST` to the `/register` route's `methods` list
  - Import `redirect`, `url_for`, `request`, `session` from `flask`
  - Import `generate_password_hash` from `werkzeug.security`
  - Implement the POST handler (see Rules for implementation)
  - Update `/register` template render to pass `name` and `email` back on error

> **Note:** Do **not** import `flash` — this spec uses the `error=` template variable
> pattern for error display, not the flash message system. Adding `flash` would be dead code.

## Files to create
None.

## New dependencies
No new dependencies. `werkzeug` is already installed as a Flask dependency.

## Rules for implementation

### General
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never string-format SQL
- Hash passwords with `werkzeug.security.generate_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`

### secret_key
Set `app.secret_key` before any route definitions. Use this exact format so it
is never silently shipped to production:

```python
app.secret_key = "dev-secret-change-in-production"  # TODO: load from env var in production
```

### Validation (run in this order — stop at first failure)
1. All three fields (`name`, `email`, `password`) must be non-empty
2. `email` must contain `@` and at least one `.` after the `@` — a minimal format check
3. `password` must be at least 8 characters long

### Database insert
- Retrieve a connection via `get_db()`
- Call `.cursor()` to get a cursor
- Use a parameterised `INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)`
- After a successful insert, read `cursor.lastrowid` — this is the new user's `id`
- Call `conn.commit()` before closing
- Wrap in `try/finally` (or `with`) to ensure `conn.close()` is always called

```python
conn = get_db()
try:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    conn.commit()
    user_id = cur.lastrowid
finally:
    conn.close()
```

### Session and redirect
- After the successful insert set `session['user_id'] = user_id` (using `lastrowid` from above)
- Redirect to `/login` — the login flow is implemented in Step 03

> **Note:** Session clearing (logout) is out of scope for this step and will be handled in Step 03.

### Duplicate email
- Catch `sqlite3.IntegrityError` around the INSERT to detect a UNIQUE constraint violation
- Re-render `register.html` with `error="Email already registered."`, `name=name`, `email=email`

### Error re-render
On any validation error or duplicate email, re-render `register.html` passing:
- `error=<message>` — shown by the existing `{% if error %}` block
- `name=<submitted value>` — repopulates the name field
- `email=<submitted value>` — repopulates the email field

Password is intentionally **not** re-populated (standard security practice).

### CSRF
CSRF protection is out of scope for this step. Add a note in the code:
`# TODO: add CSRF protection (e.g. Flask-WTF) before production deployment`

## Definition of done
- [ ] `GET /register` still renders the form unchanged
- [ ] Submitting empty fields shows a validation error without crashing
- [ ] Submitting an invalid email format (no `@`) shows a validation error
- [ ] Submitting a password shorter than 8 characters shows an error
- [ ] Submitting a duplicate email shows "Email already registered." (or similar)
- [ ] A valid submission inserts a row into `users` with a hashed (not plain-text) password
- [ ] After success `session['user_id']` is set to the new user's integer id
- [ ] After success the browser is redirected to `/login`
- [ ] After a failed submission the name and email fields are re-populated (password field is empty)
- [ ] App starts without errors (`python app.py`)