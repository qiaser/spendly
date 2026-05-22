---
name: spendly-profile-page
description: Generate a complete, production-ready Profile Page for the Spendly Flask + Jinja2 expense tracker. Includes a view template (avatar with initials fallback, account info, monthly spending stats, recent transactions count), a separate edit-profile form (name/email/password with save & cancel), the Flask route handlers, and CSS additions that use the project's existing design tokens. Use this skill whenever the user asks for a profile page, account page, user settings page, profile screen, profile template, "/profile" route, or any user-account UI in the Spendly codebase — even if they don't say "profile" explicitly (e.g. "let users edit their name and email", "show how much I've spent this month on my account page", "build the settings screen"). Also use it when the user references the existing stub at `@app.route("/profile")` in `app.py` and wants it filled in.
---

# Spendly Profile Page

This skill turns Spendly's stub `/profile` route into a working, on-brand profile and settings page. Spendly is a teaching codebase, so the goal isn't just to dump code — it's to produce code that drops in cleanly and to explain the moves so the user learns from them.

## Why this skill exists

Spendly has hard project conventions that are easy to violate by reflex:

- Auth is **session-based via `session["user_id"]`** — there is no `flask_login`, so `@login_required` is wrong here.
- DB access goes through **`get_db()` in `database/db.py`** with `sqlite3.Row` row factory — connections are opened and closed per request via `try/finally`.
- All pages **extend `templates/base.html`** (which provides the navbar, footer, and loads the global stylesheet). Templates are page fragments, not standalone HTML documents.
- Styling uses **CSS custom properties defined in `static/css/style.css`** (`--ink`, `--paper-card`, `--accent`, `--accent-2`, etc.). The CLAUDE.md in this repo explicitly says: never hardcode colors or fonts.
- There is **no ORM** — raw SQLite, parameterized queries.

A profile page written without these in mind looks plausible but breaks the build or clashes with the rest of the app. Following the steps below avoids that.

## Step 1 — Inspect before writing

Before generating anything, read these files from the repo so the output matches reality:

1. `app.py` — confirm the existing `/profile` stub is still `return "Profile page — coming in Step 4"`, and note the imports already present (`session`, `redirect`, `url_for`, `render_template`, `request`, `generate_password_hash`, `check_password_hash`, `get_db`).
2. `database/db.py` — check whether `users` and `expenses` tables are defined yet. If `expenses` isn't there, the spending stats will need to degrade gracefully (return zeros). The schema-introspection helper below handles this at runtime.
3. `templates/base.html` — confirm which `{% block %}` names exist (typically `title`, `content`, and `scripts`). Use them verbatim.
4. `static/css/style.css` — confirm the design tokens listed in `CLAUDE.md`. If any token name in this skill doesn't exist in the actual stylesheet, switch to the closest one that does rather than inventing a new one.

If any of these files look meaningfully different from what's described here, surface the difference to the user before generating code. Don't silently paper over it.

## Step 2 — Explain what you're about to build

Before emitting code, give the user a short plan:

> "I'll add three things: a `/profile` route that reads the logged-in user and their spending stats from SQLite, a `profile.html` template that shows the avatar + stats + 'Edit profile' link, and an `edit_profile.html` template with the name/email/password form. I'll also add a small block of CSS using your existing design tokens. The new route will replace the stub at line ~117 of `app.py`."

This step matters because Spendly is a teaching scaffold. Students are meant to understand changes, not just accept them.

## Step 3 — Write the schema-introspection helper

Spending stats depend on an `expenses` table whose exact schema is implemented by students, so the route shouldn't assume specific column names. Add this helper near the top of `app.py` (just under the imports), once:

```python
def _expenses_columns(conn):
    """Return the set of column names on the expenses table, or empty set if it doesn't exist yet."""
    try:
        rows = conn.execute("PRAGMA table_info(expenses)").fetchall()
        return {row["name"] for row in rows}
    except Exception:
        return set()
```

The route uses this to decide whether to query stats at all, and to pick the right column names (`amount` is near-universal; the date column is commonly `date`, `created_at`, or `spent_on`; category is commonly `category`).

## Step 4 — Replace the `/profile` stub

Find the existing stub in `app.py`:

```python
@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"
```

Replace it with the route below. Note the auth guard — `session.get("user_id")` returning `None` means not logged in, redirect to `/login`.

```python
from datetime import datetime  # add to existing imports at top of file

@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            session.clear()
            return redirect(url_for("login"))

        # Spending stats — degrade gracefully if expenses table isn't ready yet
        stats = {
            "total_this_month": 0.0,
            "budget_used_pct": 0,
            "top_category": "—",
            "recent_count": 0,
        }
        cols = _expenses_columns(conn)
        if {"amount", "user_id"}.issubset(cols):
            # Pick whichever date column the student implemented
            date_col = next((c for c in ("date", "spent_on", "created_at") if c in cols), None)
            month_clause = f"AND strftime('%Y-%m', {date_col}) = strftime('%Y-%m', 'now')" if date_col else ""

            total_row = conn.execute(
                f"SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ? {month_clause}",
                (user_id,),
            ).fetchone()
            stats["total_this_month"] = float(total_row["total"] or 0)

            if "category" in cols:
                top_row = conn.execute(
                    f"""
                    SELECT category, SUM(amount) AS s
                    FROM expenses
                    WHERE user_id = ? {month_clause}
                    GROUP BY category
                    ORDER BY s DESC
                    LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
                if top_row and top_row["category"]:
                    stats["top_category"] = top_row["category"]

            count_row = conn.execute(
                "SELECT COUNT(*) AS c FROM expenses WHERE user_id = ?", (user_id,)
            ).fetchone()
            stats["recent_count"] = int(count_row["c"] or 0)

            # Budget used % — Spendly doesn't have a budgets table yet, so use a soft default of $500/month.
            # When students add a budgets table, swap this for a real query.
            monthly_budget = 500.0
            stats["budget_used_pct"] = min(round(stats["total_this_month"] / monthly_budget * 100), 100) if monthly_budget else 0
    finally:
        conn.close()

    initials = "".join(part[:1].upper() for part in user["name"].split()[:2]) or "?"
    return render_template("profile.html", user=user, stats=stats, initials=initials)
```

Note the deliberate choices:

- **Parameterized SQL everywhere.** String interpolation is only used for column names (which come from a hardcoded allow-list, not user input).
- **`COALESCE(SUM(...), 0)`** so the query never returns `None` for users with no expenses yet.
- **The monthly budget is a soft constant.** A real budgets feature doesn't exist in the codebase yet; the comment flags this so the student knows where to wire it in later.
- **Initials fallback computed in Python**, not Jinja — keeps the template clean.

## Step 5 — Add the edit-profile route

Add this right after the `/profile` route. It handles both rendering the form (GET) and processing the submission (POST). Password change is optional — if both password fields are blank, only name/email are updated.

```python
@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            session.clear()
            return redirect(url_for("login"))

        if request.method == "GET":
            return render_template("edit_profile.html", user=user)

        # POST
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")

        # Validation
        if not name or not email:
            return render_template("edit_profile.html", user=user,
                                   error="Name and email are required.",
                                   form={"name": name, "email": email})
        if "@" not in email or "." not in email.split("@")[-1]:
            return render_template("edit_profile.html", user=user,
                                   error="Enter a valid email address.",
                                   form={"name": name, "email": email})

        # If they're trying to change the password, current_password must verify
        if new_password:
            if len(new_password) < 8:
                return render_template("edit_profile.html", user=user,
                                       error="New password must be at least 8 characters.",
                                       form={"name": name, "email": email})
            current_hash_row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not check_password_hash(current_hash_row["password_hash"], current_password):
                return render_template("edit_profile.html", user=user,
                                       error="Current password is incorrect.",
                                       form={"name": name, "email": email})

        # Apply update
        try:
            if new_password:
                conn.execute(
                    "UPDATE users SET name = ?, email = ?, password_hash = ? WHERE id = ?",
                    (name, email, generate_password_hash(new_password), user_id),
                )
            else:
                conn.execute(
                    "UPDATE users SET name = ?, email = ? WHERE id = ?",
                    (name, email, user_id),
                )
            conn.commit()
        except sqlite3.IntegrityError:
            return render_template("edit_profile.html", user=user,
                                   error="That email is already taken.",
                                   form={"name": name, "email": email})
    finally:
        conn.close()

    return redirect(url_for("profile"))
```

Why a separate route instead of one combined view: it keeps `/profile` cheap to load (no form state to manage), and it gives the user a clean URL to bookmark or link to. The Cancel button on the form just `href`s back to `/profile`.

## Step 6 — Create `templates/profile.html`

This extends `base.html` so the navbar + footer come for free. Use the existing block names — confirm them in `base.html` first; if `content` isn't the block name, use whatever is.

```html
{% extends "base.html" %}

{% block title %}Profile — Spendly{% endblock %}

{% block content %}
<section class="profile-page">

  <header class="profile-header">
    <div class="avatar" aria-hidden="true">{{ initials }}</div>
    <div class="profile-identity">
      <h1 class="profile-name">{{ user.name }}</h1>
      <p class="profile-email">{{ user.email }}</p>
    </div>
    <a class="btn btn-secondary" href="{{ url_for('edit_profile') }}">Edit profile</a>
  </header>

  <h2 class="section-title">This month</h2>
  <div class="stats-grid">
    <article class="stat-card">
      <p class="stat-label">Total spent</p>
      <p class="stat-value">${{ "%.2f"|format(stats.total_this_month) }}</p>
    </article>

    <article class="stat-card">
      <p class="stat-label">Budget used</p>
      <p class="stat-value">{{ stats.budget_used_pct }}%</p>
      <div class="progress" role="progressbar"
           aria-valuenow="{{ stats.budget_used_pct }}" aria-valuemin="0" aria-valuemax="100">
        <div class="progress-fill" style="width: {{ stats.budget_used_pct }}%"></div>
      </div>
    </article>

    <article class="stat-card">
      <p class="stat-label">Top category</p>
      <p class="stat-value stat-value--text">{{ stats.top_category }}</p>
    </article>

    <article class="stat-card">
      <p class="stat-label">Recent transactions</p>
      <p class="stat-value">{{ stats.recent_count }}</p>
    </article>
  </div>

  {% if stats.recent_count == 0 %}
    <p class="empty-hint">No transactions yet. <a href="{{ url_for('add_expense') }}">Add your first expense</a> to start tracking.</p>
  {% endif %}

</section>
{% endblock %}
```

Why `style="width: {{ ... }}%"` is acceptable here even though inline styles are usually frowned on: the value is a server-computed integer, not user input, and the alternative (a CSS variable per render) costs more than it gains for this one bar. If the rest of the codebase uses CSS variables for similar progress patterns, follow that instead.

## Step 7 — Create `templates/edit_profile.html`

```html
{% extends "base.html" %}

{% block title %}Edit profile — Spendly{% endblock %}

{% block content %}
<section class="profile-edit">
  <h1 class="section-title">Edit profile</h1>

  {% if error %}
    <p class="form-error" role="alert">{{ error }}</p>
  {% endif %}

  <form method="post" action="{{ url_for('edit_profile') }}" class="profile-form" novalidate>
    <label class="field">
      <span class="field-label">Name</span>
      <input type="text" name="name" required
             value="{{ form.name if form else user.name }}">
    </label>

    <label class="field">
      <span class="field-label">Email</span>
      <input type="email" name="email" required
             value="{{ form.email if form else user.email }}">
    </label>

    <fieldset class="field-group">
      <legend>Change password (optional)</legend>

      <label class="field">
        <span class="field-label">Current password</span>
        <input type="password" name="current_password" autocomplete="current-password">
      </label>

      <label class="field">
        <span class="field-label">New password</span>
        <input type="password" name="new_password" autocomplete="new-password"
               minlength="8">
        <span class="field-hint">At least 8 characters. Leave blank to keep your current password.</span>
      </label>
    </fieldset>

    <div class="form-actions">
      <a class="btn btn-secondary" href="{{ url_for('profile') }}">Cancel</a>
      <button type="submit" class="btn btn-primary">Save changes</button>
    </div>
  </form>
</section>
{% endblock %}
```

Note: `name="current_password"` and `name="new_password"` match exactly what the route reads via `request.form.get(...)`. If you rename one, rename both.

## Step 8 — Add CSS to `static/css/style.css`

Append to the existing stylesheet. Every color, font, and radius below references a token already defined in the project — don't introduce new tokens, and don't hardcode hex values. If a token name here doesn't actually exist in your `style.css`, swap to the closest existing one.

```css
/* ---------- Profile page ---------- */

.profile-page,
.profile-edit {
  max-width: var(--max-width);
  margin: 2rem auto;
  padding: 0 1.5rem;
}

.profile-header {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 2rem;
  background: var(--paper-card);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-lg);
  margin-bottom: 2.5rem;
}

.avatar {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: var(--accent);
  color: var(--paper);
  font-family: var(--font-display);
  font-size: 1.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  letter-spacing: 0.02em;
}

.profile-identity { flex: 1; min-width: 0; }
.profile-name { font-family: var(--font-display); margin: 0; color: var(--ink); }
.profile-email { color: var(--ink-muted); margin: 0.25rem 0 0; }

.section-title {
  font-family: var(--font-display);
  color: var(--ink);
  margin: 0 0 1rem;
}

/* Stats grid */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.stat-card {
  background: var(--paper-card);
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  padding: 1.25rem;
}

.stat-label {
  color: var(--ink-muted);
  font-size: 0.875rem;
  margin: 0 0 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.stat-value {
  font-family: var(--font-display);
  font-size: 1.75rem;
  color: var(--ink);
  margin: 0;
}

.stat-value--text { font-size: 1.25rem; }

.progress {
  height: 6px;
  background: var(--accent-light);
  border-radius: var(--radius-sm);
  margin-top: 0.75rem;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent);
  transition: width 200ms ease;
}

.empty-hint {
  color: var(--ink-muted);
  margin-top: 2rem;
  text-align: center;
}

/* Edit form */
.profile-form { display: flex; flex-direction: column; gap: 1.25rem; max-width: var(--auth-width); }

.field { display: flex; flex-direction: column; gap: 0.4rem; }
.field-label { color: var(--ink-soft); font-size: 0.9rem; }
.field input {
  padding: 0.65rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--paper);
  color: var(--ink);
  font-family: var(--font-body);
}
.field input:focus { outline: 2px solid var(--accent); outline-offset: 1px; }
.field-hint { color: var(--ink-faint); font-size: 0.8rem; }

.field-group {
  border: 1px solid var(--border-soft);
  border-radius: var(--radius-md);
  padding: 1rem 1.25rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.field-group legend { color: var(--ink-soft); padding: 0 0.4rem; }

.form-error {
  background: var(--danger-light);
  color: var(--danger);
  padding: 0.75rem 1rem;
  border-radius: var(--radius-sm);
  margin-bottom: 1rem;
}

.form-actions { display: flex; gap: 0.75rem; justify-content: flex-end; }

/* Mobile */
@media (max-width: 600px) {
  .profile-header { flex-direction: column; align-items: flex-start; text-align: left; }
  .form-actions { flex-direction: column-reverse; }
  .form-actions .btn { width: 100%; }
}
```

If the project doesn't already have `.btn`, `.btn-primary`, `.btn-secondary` classes, check `style.css` for whatever convention exists (e.g. `.button--primary`) and adapt the HTML in both templates to match. Don't define button styles in this skill unless you've confirmed they're missing.

## Step 9 — Verify and summarize

After making the edits, tell the user:

1. What files changed and where.
2. To restart the dev server: `python app.py`, then visit `http://localhost:5001/profile` after logging in.
3. That the budget bar uses a placeholder of $500/month, and where to swap in a real budgets query when that feature exists.
4. To check that `.btn-primary`/`.btn-secondary` class names actually exist in their stylesheet — if not, point at the one line in each template to update.

## What not to do

A few common reflexes that produce wrong code for this codebase:

- **Don't add `flask_login` or `@login_required`.** The project uses raw session keys.
- **Don't hardcode colors like `#10b981` or `#fff`.** Every color comes from a CSS custom property.
- **Don't write a full `<html>` document in the templates.** They extend `base.html`.
- **Don't add Bootstrap.** The project is plain CSS with design tokens, and adding a framework would clash with the existing styles.
- **Don't use string formatting for SQL parameters.** Always use `?` placeholders and tuple arguments — except for column names that come from the hardcoded allow-list in `_expenses_columns`.
- **Don't create a `models.py` or introduce SQLAlchemy.** Raw SQLite is a deliberate teaching choice in this codebase.