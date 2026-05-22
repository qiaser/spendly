import sqlite3

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = "dev-secret-change-in-production"  # TODO: load from env var in production


def _expenses_columns(conn):
    try:
        rows = conn.execute("PRAGMA table_info(expenses)").fetchall()
        return {row["name"] for row in rows}
    except Exception:
        return set()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("profile"))
        return render_template("register.html")

    # TODO: add CSRF protection (e.g. Flask-WTF) before production deployment
    name     = request.form.get("name",     "").strip()
    email    = request.form.get("email",    "").strip()
    password = request.form.get("password", "").strip()

    if not name or not email or not password:
        return render_template("register.html",
                               error="All fields are required.",
                               name=name, email=email)

    if "@" not in email or "." not in email.split("@")[-1]:
        return render_template("register.html",
                               error="Enter a valid email address.",
                               name=name, email=email)

    if len(password) < 8:
        return render_template("register.html",
                               error="Password must be at least 8 characters.",
                               name=name, email=email)

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return render_template("register.html",
                               error="Email already registered.",
                               name=name, email=email)
    finally:
        conn.close()

    session["user_id"] = user_id
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("profile"))
        return render_template("login.html")

    email    = request.form.get("email",    "").strip()
    password = request.form.get("password", "").strip()

    if not email or not password:
        return render_template("login.html",
                               error="All fields are required.",
                               email=email)

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()

    if row is None or not check_password_hash(row["password_hash"], password):
        return render_template("login.html",
                               error="Invalid email or password.",
                               email=email)

    session["user_id"] = row["id"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


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

        stats = {
            "total_this_month": 0.0,
            "budget_used_pct": 0,
            "top_category": "—",
            "recent_count": 0,
        }
        cols = _expenses_columns(conn)
        if {"amount", "user_id"}.issubset(cols):
            date_col = next((c for c in ("date", "spent_on", "created_at") if c in cols), None)
            month_clause = (
                f"AND strftime('%Y-%m', {date_col}) = strftime('%Y-%m', 'now')"
                if date_col else ""
            )

            total_row = conn.execute(
                f"SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE user_id = ? {month_clause}",
                (user_id,),
            ).fetchone()
            stats["total_this_month"] = float(total_row["total"] or 0)

            if "category" in cols:
                top_row = conn.execute(
                    f"""SELECT category, SUM(amount) AS s
                    FROM expenses WHERE user_id = ? {month_clause}
                    GROUP BY category ORDER BY s DESC LIMIT 1""",
                    (user_id,),
                ).fetchone()
                if top_row and top_row["category"]:
                    stats["top_category"] = top_row["category"]

            count_row = conn.execute(
                "SELECT COUNT(*) AS c FROM expenses WHERE user_id = ?", (user_id,)
            ).fetchone()
            stats["recent_count"] = int(count_row["c"] or 0)

            monthly_budget = 500.0
            stats["budget_used_pct"] = (
                min(round(stats["total_this_month"] / monthly_budget * 100), 100)
                if monthly_budget else 0
            )
    finally:
        conn.close()

    initials = "".join(part[:1].upper() for part in user["name"].split()[:2]) or "?"
    return render_template("profile.html", user=user, stats=stats, initials=initials)


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

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")

        if not name or not email:
            return render_template("edit_profile.html", user=user,
                                   error="Name and email are required.",
                                   form={"name": name, "email": email})

        if "@" not in email or "." not in email.split("@")[-1]:
            return render_template("edit_profile.html", user=user,
                                   error="Enter a valid email address.",
                                   form={"name": name, "email": email})

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


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


with app.app_context():
    init_db()
    seed_db()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
