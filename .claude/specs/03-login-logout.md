# Spec: Login and Logout

## Overview
Implement full login and logout functionality for Spendly. The `/login` route already
handles GET (renders the form) but has no POST handler. This step adds form processing:
validate credentials, verify the password hash, write the user id to the Flask session,
and redirect to the profile page. The `/logout` route currently returns a placeholder
string; this step replaces it with a session-clearing redirect back to the login page.

## Depends on
- Step 01 — Database Setup (`users` table must exist; `get_db()` must be functional)
- Step 02 — Registration (at least one user must exist; the seeded demo user is sufficient)

## Routes
- `GET  /login`  — render login form — public (no change needed)
- `POST /login`  — validate credentials, set session, redirect to profile — public
- `GET  /logout` — clear session, redirect to `/login` — no auth guard required this step

## Database changes
No database changes. The `users` table already has `email` and `password_hash`.

## Templates
- **Modify:** `templates/login.html`
  - Add `method="POST"` to the `<form>` element (action can be omitted — defaults to current URL)
  - Render `{{ error }}` message when present (use the same pattern as `register.html`)
  - Re-populate the `email` field via `value="{{ email or '' }}"` on failed login
  - Password field is **never** re-populated

## Files to change
- `app.py`
  - Import `check_password_hash` from `werkzeug.security` (add alongside existing import)
  - Change `/login` route decorator to `methods=["GET", "POST"]`
  - Implement the POST handler (see Rules for implementation)
  - Replace the `/logout` stub body with session-clearing logic

## Files to create
None.

## New dependencies
No new dependencies. `werkzeug` is already installed as a Flask dependency.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never string-format SQL
- Passwords verified with `werkzeug.security.check_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`

### Login POST handler (run in this order)
1. Read `email` and `password` from `request.form`, `.strip()` both
2. If either field is empty → re-render `login.html` with `error="All fields are required."` and `email=email`
3. Query the database: `SELECT id, password_hash FROM users WHERE email = ?`
4. If no row found **or** `check_password_hash(row['password_hash'], password)` returns `False` →
   re-render `login.html` with `error="Invalid email or password."` and `email=email`
   (use the same message for both cases — do not reveal which field is wrong)
5. On success: `session['user_id'] = row['id']`, then `redirect(url_for('profile'))`
6. Always close the db connection (use `try/finally`)

```python
conn = get_db()
try:
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE email = ?", (email,)
    ).fetchone()
finally:
    conn.close()
```

### Logout handler
```python
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
```

### Error re-render
Pass to `render_template("login.html", ...)`:
- `error=<message string>`
- `email=<submitted email value>` — repopulates the email field

Password is intentionally **not** re-populated (standard security practice).

## Definition of done
- [ ] `GET /login` still renders the form unchanged
- [ ] Submitting empty fields shows "All fields are required." without crashing
- [ ] Submitting a non-existent email shows "Invalid email or password."
- [ ] Submitting the correct email with the wrong password shows "Invalid email or password."
- [ ] Submitting valid credentials (`demo@spendly.com` / `demo123`) sets `session['user_id']` and redirects to `/profile`
- [ ] After a failed login the email field is re-populated and the password field is empty
- [ ] Visiting `/logout` clears the session and redirects to `/login`
- [ ] App starts without errors (`python app.py`)
