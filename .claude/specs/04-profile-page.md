# Spec: Profile Page

## Overview
Implement the `/profile` route that is currently a stub returning a placeholder string.
This step gives authenticated users a dedicated page showing their account information
(name, email, member-since date), a spending summary for the current month, and a count
of recent transactions pulled live from the `expenses` table. A companion `/profile/edit`
route lets users update their name, email, and optionally change their password. Together
these routes replace every `"Profile page — coming in Step 4"` stub and establish the
post-login landing page that `/register` and `/login` already redirect to.

## Depends on
- Step 01 — Database Setup (`get_db()`, `users` table, `expenses` table must exist)
- Step 02 — Registration (at least one user row must exist)
- Step 03 — Login and Logout (`session['user_id']` must be set by the login flow)

## Routes
- `GET  /profile`       — display profile view with account info and spending stats — logged-in only
- `GET  /profile/edit`  — render the edit-profile form pre-filled with current values — logged-in only
- `POST /profile/edit`  — validate and save name/email/password changes — logged-in only

## Database changes
No new tables or columns. All required data (`name`, `email`, `created_at`) already exists
in the `users` table, and spending data is in `expenses`. Always verify against `database/db.py`.

## Templates
- **Create:** `templates/profile.html`
  - Extends `base.html`
  - Avatar circle showing the user's initials (first letter of name) as a CSS-drawn fallback
  - Account info card: full name, email, member since (formatted `created_at`)
  - Stats row: total expenses this month (sum of `amount`), number of transactions this month
  - Link/button to `/profile/edit`

- **Create:** `templates/profile_edit.html`
  - Extends `base.html`
  - Form with fields: Name (text), Email (email), New Password (password, optional),
    Confirm Password (password, optional)
  - Pre-fills Name and Email from current user data
  - Save button and Cancel link back to `/profile`
  - Renders `{{ error }}` and `{{ success }}` flash messages

## Files to change
- `app.py`
  - Replace the `/profile` stub with a full GET handler (auth guard + DB query + template render)
  - Add `GET /profile/edit` and `POST /profile/edit` route (same function, `methods=["GET","POST"]`)

- `static/css/style.css`
  - Add avatar circle styles (uses `--accent`, `--font-display`, CSS custom properties only)
  - Add profile card and stats row layout classes

## Files to create
- `templates/profile.html`
- `templates/profile_edit.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never string-format SQL
- Passwords hashed with `werkzeug.security.generate_password_hash`; verified with `check_password_hash`
- Use CSS variables — never hardcode hex values or font names directly
- All templates extend `base.html`
- Auth guard: if `session.get("user_id")` is falsy, `redirect(url_for("login"))`
- Apply the auth guard at the top of every profile route handler before any DB call
- Monthly stats query must filter by the current year+month using `strftime('%Y-%m', date)`
- Password change is optional: only hash and update if the new-password field is non-empty
- If new password is provided, Confirm Password must match — re-render form with error if not
- Email uniqueness: catch `sqlite3.IntegrityError` on UPDATE and re-render with a meaningful error
- Always close DB connections in a `try/finally` block

### Auth guard pattern
```python
if not session.get("user_id"):
    return redirect(url_for("login"))
```

### Monthly stats query
```python
import datetime
now = datetime.date.today()
month_str = now.strftime("%Y-%m")
row = conn.execute(
    "SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total "
    "FROM expenses WHERE user_id = ? AND strftime('%Y-%m', date) = ?",
    (user_id, month_str),
).fetchone()
```

### Profile edit POST flow (run in this order)
1. Auth guard
2. Read `name`, `email`, `new_password`, `confirm_password` from `request.form`, `.strip()` all
3. If `name` or `email` is empty → re-render form with `error="Name and email are required."`
4. If `new_password` is non-empty and `new_password != confirm_password` →
   re-render form with `error="Passwords do not match."`
5. If `new_password` is non-empty and `len(new_password) < 8` →
   re-render form with `error="Password must be at least 8 characters."`
6. Build the UPDATE: if password provided, update `name`, `email`, `password_hash`;
   otherwise update only `name` and `email`
7. Catch `sqlite3.IntegrityError` → re-render form with `error="Email already in use."`
8. On success: update `session` if needed, redirect to `/profile` with a `success` flash

## Definition of done
- [ ] Visiting `/profile` without being logged in redirects to `/login`
- [ ] After logging in, `/profile` renders without errors and shows the user's name and email
- [ ] The avatar circle displays the first letter of the user's name
- [ ] The monthly stats row shows a spend total and transaction count (even if both are 0)
- [ ] Clicking the edit link opens `/profile/edit` pre-filled with the current name and email
- [ ] Submitting the edit form with a new name saves it and the profile page reflects the change
- [ ] Submitting the edit form with mismatched passwords shows "Passwords do not match."
- [ ] Submitting the edit form with a duplicate email shows "Email already in use."
- [ ] Leaving the password fields blank performs a name/email-only update (no password change)
- [ ] App starts without errors (`python app.py`)
