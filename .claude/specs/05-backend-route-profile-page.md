# Spec: Backend Route for Profile Page

## Overview
Wire the `/profile` and `/profile/edit` routes to the live SQLite database so the
profile template receives real user data, monthly spending stats, category breakdowns,
and transaction history. Step 04 produced the HTML template; this step makes the
backend route fetch and compute all the values that template expects. It also implements
the edit-profile POST handler that validates and persists name, email, and optional
password changes. After this step the profile page is fully functional end-to-end.

## Depends on
- Step 01 — Database Setup (`get_db()`, `users` table, `expenses` table must exist)
- Step 02 — Registration (at least one user row must exist)
- Step 03 — Login and Logout (`session['user_id']` set by the login flow)
- Step 04 — Profile Page (`templates/profile.html` and `templates/edit_profile.html` must exist)

## Routes
- `GET  /profile`      — query DB for user + stats + transactions, render profile.html — logged-in only
- `GET  /profile/edit` — fetch current user row, render edit_profile.html pre-filled — logged-in only
- `POST /profile/edit` — validate form, update `users` row, redirect to `/profile` — logged-in only

## Database changes
No new tables or columns. All required data already exists:
- `users`: `id`, `name`, `email`, `password_hash`, `created_at`
- `expenses`: `id`, `user_id`, `amount`, `category`, `date`, `description`

## Templates
- **Modify:** `templates/profile.html`
  - Ensure variables match what the route passes: `user`, `initials`, `stats`,
    `transactions`, `category_totals`
  - `stats` dict keys: `total_this_month` (float), `budget_used_pct` (int 0–100),
    `top_category` (str), `recent_count` (int)
  - `category_totals` list: each item has `name`, `total` (float), `pct` (int)
  - `transactions` list: each row has `date`, `description`, `category`, `amount`

- **Modify:** `templates/edit_profile.html`
  - Must accept `user`, `error` (optional), and `form` (optional dict with `name`/`email`
    to re-fill after a failed POST)

## Files to change
- `app.py`
  - Replace the `/profile` stub with a full GET handler (see implementation rules below)
  - Replace the `/profile/edit` stub with GET + POST handler (same function, `methods=["GET","POST"]`)

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation

### General
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never format SQL strings with user data
- Passwords hashed with `werkzeug.security.generate_password_hash`; verified with `check_password_hash`
- Use CSS variables — never hardcode hex values or font names
- All templates extend `base.html`
- Always close DB connections in a `try/finally` block

### Auth guard (both routes, applied before any DB call)
```python
user_id = session.get("user_id")
if not user_id:
    return redirect(url_for("login"))
```

### GET /profile — data to gather
1. Fetch the user row: `SELECT id, name, email FROM users WHERE id = ?`
   - If `None`, clear session and redirect to `/login`
2. Compute `initials`: first letter of each word in `user["name"]`, max 2, upper-cased
3. Compute monthly stats (filter by current year-month with `strftime('%Y-%m', date)`):
   - `total_this_month`: `COALESCE(SUM(amount), 0)` from `expenses WHERE user_id = ? AND strftime(...)`
   - `top_category`: category with highest `SUM(amount)` this month (fall back to `"—"` if none)
   - `recent_count`: `COUNT(*)` from all expenses for this user (not month-filtered)
   - `budget_used_pct`: `min(round(total_this_month / 500.0 * 100), 100)` (hardcode budget as 500 for now)
4. Fetch `transactions`: all rows for this user ordered `date DESC`
5. Compute `category_totals`: `GROUP BY category`, calculate each category's `pct` of the grand total
6. Render `profile.html` passing all five context variables

### POST /profile/edit — validation order
1. Auth guard
2. Read and `.strip()`: `name`, `email`, `current_password`, `new_password` from `request.form`
3. If `name` or `email` empty → re-render with `error="Name and email are required."`
4. If `new_password` non-empty:
   a. If `len(new_password) < 8` → re-render with `error="Password must be at least 8 characters."`
   b. Fetch `password_hash` from DB; if `check_password_hash` fails →
      re-render with `error="Current password is incorrect."`
5. Build UPDATE: include `password_hash` only when `new_password` is non-empty
6. Catch `sqlite3.IntegrityError` → re-render with `error="That email is already taken."`
7. On success: `conn.commit()` then `redirect(url_for("profile"))`

## Definition of done
- [ ] `GET /profile` without a session redirects to `/login`
- [ ] After login, `/profile` renders and shows the logged-in user's name and email
- [ ] The avatar circle shows the correct initials (e.g. "Demo User" → "DU")
- [ ] `total_this_month` shows the correct sum of this month's expenses (not 0 when expenses exist)
- [ ] `top_category` shows the category with the highest spend this month
- [ ] `recent_count` reflects the actual number of expense rows for this user
- [ ] The transaction table lists all expenses for the user, newest first
- [ ] The category breakdown bars render with correct percentages
- [ ] `GET /profile/edit` renders the form pre-filled with the current name and email
- [ ] Submitting the edit form with a new name updates it and the profile page reflects the change
- [ ] Submitting with a short new password shows the minimum-length error
- [ ] Submitting with a wrong current password shows the incorrect-password error
- [ ] Submitting with a duplicate email shows "That email is already taken."
- [ ] Leaving password fields blank performs a name/email-only update
- [ ] App starts without errors (`python app.py`)
