# Spec: Date Filter for Profile Page

## Overview
Add a date-range filter to the profile page so users can narrow the transactions list,
spending stats, and category breakdown to a specific period. The filter is driven by a
`?period=` query-string parameter (values: `month`, `30d`, `90d`, `all`) so it is
bookmarkable and requires no JavaScript. The profile route already computes stats and
transactions via three private helpers; this step extends those helpers to accept
`date_from` / `date_to` bounds, and updates the template to render a filter bar.

## Depends on
- Step 01 — Database Setup (`expenses` table with a `date` TEXT column must exist)
- Step 02 — Registration (at least one user must exist)
- Step 03 — Login and Logout (`session['user_id']` set by login)
- Step 04 — Profile Page (`templates/profile.html` must exist)
- Step 05 — Backend Route for Profile Page (full `/profile` GET handler must be in place)

## Routes
- `GET /profile?period=<preset>` — same route as Step 05, now reads `period` query param
  and passes date bounds to all three stat/transaction helpers — logged-in only

No new routes.

## Database changes
No database changes. The `expenses.date` column (TEXT, ISO-8601 `YYYY-MM-DD`) already
supports range queries with standard `>=` / `<=` comparisons.

## Templates
- **Modify:** `templates/profile.html`
  - Add a filter bar above the transactions section with four period buttons:
    - "This Month" (`?period=month`) — default
    - "Last 30 Days" (`?period=30d`)
    - "Last 90 Days" (`?period=90d`)
    - "All Time" (`?period=all`)
  - The active period button should carry an `active` CSS class
  - Stats section heading and transaction-count badge should reflect the active period label
    (e.g. "Spending this month" → "Spending — Last 30 Days")
  - Pass `active_period` string from the route to the template for the active-button logic

## Files to change
- `app.py`
  - `_profile_transactions(conn, user_id, cols)` → add `date_from: str | None, date_to: str | None`
    parameters; append `AND date >= ? AND date <= ?` to the WHERE clause when both are provided
  - `_profile_stats(conn, user_id, cols)` → same signature change; apply date bounds to
    all three sub-queries (total, count, top category)
  - `_profile_category_totals(conn, user_id, cols)` → same signature change; apply date
    bounds to the GROUP BY query
  - `profile()` route — read `period = request.args.get("period", "month")`, compute
    `date_from` / `date_to` strings from it, pass `active_period=period` to the template
- `static/css/style.css`
  - Add styles for `.filter-bar`, `.filter-btn`, and `.filter-btn.active`

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation

### General
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never format SQL strings with user data
- Passwords hashed with `werkzeug`; no password logic changes needed here
- Use CSS variables — never hardcode hex values or font names
- All templates extend `base.html`

### Period → date bounds mapping (compute in the `profile()` route)
Use Python's `datetime.date` to compute the bounds as `YYYY-MM-DD` strings:

| `period` value | `date_from`                          | `date_to`   |
|---------------|--------------------------------------|-------------|
| `month`       | first day of current month           | today       |
| `30d`         | today − 29 days                      | today       |
| `90d`         | today − 89 days                      | today       |
| `all`         | `None`                               | `None`      |

Any unrecognised value should fall back to `month`.

### Helper signature pattern
```python
def _profile_transactions(conn, user_id, cols, date_from=None, date_to=None):
    ...
    where = "WHERE user_id = ?"
    params = [user_id]
    if date_from and date_to:
        where += " AND date >= ? AND date <= ?"
        params += [date_from, date_to]
    ...
```

Apply the same pattern to `_profile_stats` and `_profile_category_totals`.

### Filter bar HTML pattern (inside `profile.html`)
```html
<div class="filter-bar">
  <a href="?period=month"  class="filter-btn {% if active_period == 'month'  %}active{% endif %}">This Month</a>
  <a href="?period=30d"    class="filter-btn {% if active_period == '30d'    %}active{% endif %}">Last 30 Days</a>
  <a href="?period=90d"    class="filter-btn {% if active_period == '90d'    %}active{% endif %}">Last 90 Days</a>
  <a href="?period=all"    class="filter-btn {% if active_period == 'all'    %}active{% endif %}">All Time</a>
</div>
```

### CSS additions (in `style.css`)
- `.filter-bar` — flex row, gap, bottom margin using existing spacing
- `.filter-btn` — uses `--paper-card`, `--border`, `--radius-sm`, `--ink-soft`; padding; no underline
- `.filter-btn.active` — `background: var(--accent)`, `color: var(--paper)`, `border-color: var(--accent)`

## Definition of done
- [ ] `GET /profile` (no query param) defaults to "This Month" and the "This Month" button is visually active
- [ ] Clicking "Last 30 Days" reloads the page with `?period=30d` and that button becomes active
- [ ] Clicking "Last 90 Days" reloads with `?period=90d` and that button becomes active
- [ ] Clicking "All Time" shows all expenses, including those outside the current month
- [ ] Switching periods changes the `total_spent` stat to reflect only expenses in that range
- [ ] Switching periods changes the `top_category` to reflect only expenses in that range
- [ ] Switching periods changes the transaction count displayed in stats
- [ ] The transactions table shows only rows within the selected date range
- [ ] The category breakdown bars recalculate percentages for the filtered set
- [ ] An unrecognised `?period=` value falls back silently to "This Month" behaviour
- [ ] App starts without errors (`python app.py`)
