"""
tests/test_06-date-filter-profile-page.py

Tests for Step 06 — Date Filter for Profile Page.

Spec: .claude/specs/06-date-filter-profile-page.md

Strategy
--------
* Every test gets its own isolated temporary SQLite file so no test shares
  state with another.
* Expenses are seeded at four known dates relative to today:
    - TODAY          → always inside `month`, `30d`, `90d`, `all`
    - 15 days ago    → inside `30d`, `90d`, `all`; may or may not be in `month`
    - 60 days ago    → inside `90d`, `all`; outside `month` and `30d`
    - 120 days ago   → inside `all` only; outside `month`, `30d`, `90d`
* Each expense uses a distinct category so category-filter assertions are
  unambiguous.
* The `get_db` function in database.db is patched (monkeypatch) to return
  connections that point at the per-test temp file.
"""

import os
import sqlite3
import tempfile
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database import db as db_module

# ---------------------------------------------------------------------------
# Date anchors (computed once at import time so every test shares the same
# reference frame for the test run)
# ---------------------------------------------------------------------------
TODAY = date.today()
DATE_TODAY = str(TODAY)
DATE_15D = str(TODAY - timedelta(days=15))
DATE_60D = str(TODAY - timedelta(days=60))
DATE_120D = str(TODAY - timedelta(days=120))

# The first day of the current month — used to decide whether the 15-day-ago
# expense falls inside the `month` window.
MONTH_START = str(TODAY.replace(day=1))

# Boolean: is the 15-days-ago expense within the current month?
_15D_IN_MONTH = DATE_15D >= MONTH_START


# ---------------------------------------------------------------------------
# Helper: build a fresh temp-file database and return its path
# ---------------------------------------------------------------------------

def _create_temp_db():
    """Create an isolated SQLite temp file, initialise schema, return path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    return path


def _seed_user(db_path, name="Test User", email="tester@example.com",
               password="securepass"):
    """Insert a single user, return their id."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return user_id


def _seed_expenses(db_path, user_id):
    """
    Insert four expenses at known dates with distinct categories and amounts.

    date        category        amount
    ----------  ----------      ------
    today       Food            10.00
    15 days ago Transport       20.00
    60 days ago Bills           40.00
    120 days ago Entertainment  80.00
    """
    rows = [
        (user_id, 10.00, "Food",          DATE_TODAY, "today expense"),
        (user_id, 20.00, "Transport",     DATE_15D,   "15d expense"),
        (user_id, 40.00, "Bills",         DATE_60D,   "60d expense"),
        (user_id, 80.00, "Entertainment", DATE_120D,  "120d expense"),
    ]
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path():
    """Provide a fresh, seeded temp SQLite database for one test."""
    path = _create_temp_db()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture()
def app(db_path, monkeypatch):
    """
    Flask app configured for testing, with get_db patched to use the
    per-test temp database file.
    """
    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })

    def _patched_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(db_module, "get_db", _patched_get_db)

    # Also patch the reference imported directly inside app.py
    import app as app_module
    monkeypatch.setattr(app_module, "get_db", _patched_get_db)

    with flask_app.app_context():
        yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def seeded_db(db_path):
    """Seed a user and expenses; return (db_path, user_id, email, password)."""
    user_id = _seed_user(db_path)
    _seed_expenses(db_path, user_id)
    return db_path, user_id, "tester@example.com", "securepass"


@pytest.fixture()
def auth_client(client, seeded_db):
    """
    A test client that is already logged in as the seeded test user.
    The seeded user has four expenses at today, 15d, 60d, 120d.
    """
    _, _, email, password = seeded_db
    client.post("/login", data={"email": email, "password": password},
                follow_redirects=False)
    return client


# ---------------------------------------------------------------------------
# Helper used in multiple tests
# ---------------------------------------------------------------------------

def get_profile(client, period=None):
    """GET /profile with an optional period query param."""
    url = "/profile" if period is None else f"/profile?period={period}"
    return client.get(url)


# ===========================================================================
# 1. Auth guard
# ===========================================================================

class TestAuthGuard:
    def test_unauthenticated_get_profile_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302, (
            "Unauthenticated /profile must redirect (302)"
        )
        location = response.headers.get("Location", "")
        assert "/login" in location, (
            f"Redirect target should be /login, got: {location}"
        )

    def test_unauthenticated_get_profile_with_period_redirects_to_login(
        self, client
    ):
        response = client.get("/profile?period=all")
        assert response.status_code == 302
        location = response.headers.get("Location", "")
        assert "/login" in location, (
            "Unauthenticated /profile?period=all must redirect to /login"
        )


# ===========================================================================
# 2. Default behavior — no query param defaults to 'month'
# ===========================================================================

class TestDefaultPeriod:
    def test_no_period_param_returns_200(self, auth_client):
        response = get_profile(auth_client)
        assert response.status_code == 200, (
            "GET /profile with no period param should return 200"
        )

    def test_no_period_param_this_month_button_is_active(self, auth_client):
        response = get_profile(auth_client)
        html = response.data.decode()
        # The "This Month" filter-btn must carry the active class
        assert 'filter-btn active' in html or 'filter-btn" active' in html or (
            'class="filter-btn active"' in html
            or "class='filter-btn active'" in html
        ), "This Month button must have active class when no period param is given"

    def test_no_period_param_month_link_has_active(self, auth_client):
        response = get_profile(auth_client)
        html = response.data.decode()
        # The anchor that points to ?period=month should carry active
        assert "?period=month" in html, "Filter bar must contain ?period=month link"
        # Verify the active class appears near the month link
        month_link_idx = html.index("?period=month")
        snippet = html[max(0, month_link_idx - 50): month_link_idx + 150]
        assert "active" in snippet, (
            "The ?period=month anchor must carry the active class when no param supplied"
        )

    def test_no_period_param_filter_bar_present(self, auth_client):
        response = get_profile(auth_client)
        html = response.data.decode()
        assert "filter-bar" in html, "filter-bar element must be present on profile page"
        assert "This Month" in html, "Filter bar must contain 'This Month' button text"
        assert "Last 30 Days" in html, "Filter bar must contain 'Last 30 Days' button text"
        assert "Last 90 Days" in html, "Filter bar must contain 'Last 90 Days' button text"
        assert "All Time" in html, "Filter bar must contain 'All Time' button text"


# ===========================================================================
# 3. ?period=month — explicit month filter
# ===========================================================================

class TestPeriodMonth:
    def test_period_month_returns_200(self, auth_client):
        response = get_profile(auth_client, "month")
        assert response.status_code == 200

    def test_period_month_active_button(self, auth_client):
        response = get_profile(auth_client, "month")
        html = response.data.decode()
        month_link_idx = html.index("?period=month")
        snippet = html[max(0, month_link_idx - 50): month_link_idx + 150]
        assert "active" in snippet, (
            "?period=month must make the 'This Month' button active"
        )

    def test_period_month_today_expense_included(self, auth_client):
        response = get_profile(auth_client, "month")
        html = response.data.decode()
        # The today expense (Food, $10.00) must appear
        assert "today expense" in html or "Food" in html, (
            "?period=month must include today's expense"
        )

    def test_period_month_excludes_120d_expense(self, auth_client):
        response = get_profile(auth_client, "month")
        html = response.data.decode()
        # The 120-day-old expense should not appear in month view
        assert "120d expense" not in html, (
            "?period=month must exclude the 120-days-old expense"
        )
        # Its date should not be in the page
        assert DATE_120D not in html, (
            f"Date {DATE_120D} (120d ago) must not appear in month-filtered view"
        )

    def test_period_month_excludes_60d_expense(self, auth_client):
        response = get_profile(auth_client, "month")
        html = response.data.decode()
        assert DATE_60D not in html, (
            f"Date {DATE_60D} (60d ago) must not appear in month-filtered view"
        )

    def test_period_month_transaction_count_correct(self, auth_client, seeded_db):
        """
        Month filter: only today's expense is guaranteed in current month.
        If 15d ago also falls in the current month, count should be 2.
        """
        response = get_profile(auth_client, "month")
        html = response.data.decode()
        expected_count = 2 if _15D_IN_MONTH else 1
        assert str(expected_count) in html, (
            f"transaction_count for month filter should be {expected_count}"
        )


# ===========================================================================
# 4. ?period=30d
# ===========================================================================

class TestPeriod30d:
    def test_period_30d_returns_200(self, auth_client):
        response = get_profile(auth_client, "30d")
        assert response.status_code == 200

    def test_period_30d_active_button(self, auth_client):
        response = get_profile(auth_client, "30d")
        html = response.data.decode()
        d30_link_idx = html.index("?period=30d")
        snippet = html[max(0, d30_link_idx - 50): d30_link_idx + 150]
        assert "active" in snippet, (
            "?period=30d must make the 'Last 30 Days' button active"
        )

    def test_period_30d_includes_today_expense(self, auth_client):
        response = get_profile(auth_client, "30d")
        html = response.data.decode()
        assert DATE_TODAY in html, (
            "?period=30d must include today's expense date"
        )

    def test_period_30d_includes_15d_expense(self, auth_client):
        response = get_profile(auth_client, "30d")
        html = response.data.decode()
        assert DATE_15D in html, (
            f"?period=30d must include the 15-days-ago expense ({DATE_15D})"
        )

    def test_period_30d_excludes_60d_expense(self, auth_client):
        response = get_profile(auth_client, "30d")
        html = response.data.decode()
        assert DATE_60D not in html, (
            f"?period=30d must exclude the 60-days-ago expense ({DATE_60D})"
        )

    def test_period_30d_excludes_120d_expense(self, auth_client):
        response = get_profile(auth_client, "30d")
        html = response.data.decode()
        assert DATE_120D not in html, (
            f"?period=30d must exclude the 120-days-ago expense ({DATE_120D})"
        )

    def test_period_30d_transaction_count_is_two(self, auth_client):
        # today + 15d ago = 2 expenses within last 30 days
        response = get_profile(auth_client, "30d")
        html = response.data.decode()
        assert "2" in html, "?period=30d should show transaction_count of 2"


# ===========================================================================
# 5. ?period=90d
# ===========================================================================

class TestPeriod90d:
    def test_period_90d_returns_200(self, auth_client):
        response = get_profile(auth_client, "90d")
        assert response.status_code == 200

    def test_period_90d_active_button(self, auth_client):
        response = get_profile(auth_client, "90d")
        html = response.data.decode()
        d90_link_idx = html.index("?period=90d")
        snippet = html[max(0, d90_link_idx - 50): d90_link_idx + 150]
        assert "active" in snippet, (
            "?period=90d must make the 'Last 90 Days' button active"
        )

    def test_period_90d_includes_today_expense(self, auth_client):
        response = get_profile(auth_client, "90d")
        html = response.data.decode()
        assert DATE_TODAY in html, "?period=90d must include today's expense"

    def test_period_90d_includes_15d_expense(self, auth_client):
        response = get_profile(auth_client, "90d")
        html = response.data.decode()
        assert DATE_15D in html, "?period=90d must include 15-day-ago expense"

    def test_period_90d_includes_60d_expense(self, auth_client):
        response = get_profile(auth_client, "90d")
        html = response.data.decode()
        assert DATE_60D in html, (
            f"?period=90d must include the 60-days-ago expense ({DATE_60D})"
        )

    def test_period_90d_excludes_120d_expense(self, auth_client):
        response = get_profile(auth_client, "90d")
        html = response.data.decode()
        assert DATE_120D not in html, (
            f"?period=90d must exclude the 120-days-ago expense ({DATE_120D})"
        )

    def test_period_90d_transaction_count_is_three(self, auth_client):
        # today + 15d + 60d = 3 expenses within last 90 days
        response = get_profile(auth_client, "90d")
        html = response.data.decode()
        assert "3" in html, "?period=90d should show transaction_count of 3"


# ===========================================================================
# 6. ?period=all
# ===========================================================================

class TestPeriodAll:
    def test_period_all_returns_200(self, auth_client):
        response = get_profile(auth_client, "all")
        assert response.status_code == 200

    def test_period_all_active_button(self, auth_client):
        response = get_profile(auth_client, "all")
        html = response.data.decode()
        all_link_idx = html.index("?period=all")
        snippet = html[max(0, all_link_idx - 50): all_link_idx + 150]
        assert "active" in snippet, (
            "?period=all must make the 'All Time' button active"
        )

    def test_period_all_includes_today_expense(self, auth_client):
        response = get_profile(auth_client, "all")
        html = response.data.decode()
        assert DATE_TODAY in html, "?period=all must include today's expense"

    def test_period_all_includes_15d_expense(self, auth_client):
        response = get_profile(auth_client, "all")
        html = response.data.decode()
        assert DATE_15D in html, "?period=all must include 15-day-ago expense"

    def test_period_all_includes_60d_expense(self, auth_client):
        response = get_profile(auth_client, "all")
        html = response.data.decode()
        assert DATE_60D in html, "?period=all must include 60-day-ago expense"

    def test_period_all_includes_120d_expense(self, auth_client):
        response = get_profile(auth_client, "all")
        html = response.data.decode()
        assert DATE_120D in html, (
            f"?period=all must include the 120-days-ago expense ({DATE_120D})"
        )

    def test_period_all_transaction_count_is_four(self, auth_client):
        response = get_profile(auth_client, "all")
        html = response.data.decode()
        assert "4" in html, "?period=all should show transaction_count of 4"

    def test_period_all_shows_all_categories(self, auth_client):
        response = get_profile(auth_client, "all")
        html = response.data.decode()
        for category in ("Food", "Transport", "Bills", "Entertainment"):
            assert category in html, (
                f"?period=all must include category '{category}'"
            )


# ===========================================================================
# 7. Unknown period falls back to 'month'
# ===========================================================================

class TestUnknownPeriodFallback:
    def test_unknown_period_returns_200(self, auth_client):
        response = get_profile(auth_client, "xyz")
        assert response.status_code == 200, (
            "Unrecognised period value must not crash the app"
        )

    def test_unknown_period_this_month_button_active(self, auth_client):
        response = get_profile(auth_client, "xyz")
        html = response.data.decode()
        month_link_idx = html.index("?period=month")
        snippet = html[max(0, month_link_idx - 50): month_link_idx + 150]
        assert "active" in snippet, (
            "Unrecognised period must fall back to month and activate 'This Month'"
        )

    def test_unknown_period_excludes_120d_expense(self, auth_client):
        response = get_profile(auth_client, "bogusvalue")
        html = response.data.decode()
        assert DATE_120D not in html, (
            "Unrecognised period fallback (month) must exclude 120-day-old expense"
        )

    def test_unknown_period_excludes_60d_expense(self, auth_client):
        response = get_profile(auth_client, "last-week")
        html = response.data.decode()
        assert DATE_60D not in html, (
            "Unrecognised period fallback (month) must exclude 60-day-old expense"
        )

    @pytest.mark.parametrize("bad_period", ["", "week", "MONTH", "1d", "99d", "yesterday"])
    def test_various_unknown_periods_return_200(self, auth_client, bad_period):
        url = f"/profile?period={bad_period}"
        response = auth_client.get(url)
        assert response.status_code == 200, (
            f"period='{bad_period}' must not crash the server"
        )


# ===========================================================================
# 8. Stats update per period
# ===========================================================================

class TestStatsUpdatePerPeriod:
    def test_total_spent_all_greater_than_month(self, auth_client):
        """
        Seeded data has $10 today, $20 15d ago, $40 60d ago, $80 120d ago.
        ?period=all total ($150) must be greater than ?period=month total.
        """
        response_month = get_profile(auth_client, "month")
        response_all = get_profile(auth_client, "all")
        html_month = response_month.data.decode()
        html_all = response_all.data.decode()

        # All-time total should contain 150.00
        assert "150.00" in html_all, (
            "?period=all total_spent should be $150.00 (sum of all four expenses)"
        )

        # Month total should NOT contain 150.00 (it's a subset)
        assert "150.00" not in html_month, (
            "?period=month total_spent must not equal the all-time total"
        )

    def test_total_spent_month_is_subset(self, auth_client):
        """
        Month-filtered total is either $10 (today only) or $30 (today + 15d),
        but never $150 or $130.
        """
        response = get_profile(auth_client, "month")
        html = response.data.decode()
        assert "150.00" not in html, "Month total must not include all-time expenses"
        assert "130.00" not in html, "Month total must not include 60d + 120d expenses"

    def test_total_spent_30d(self, auth_client):
        """
        30d window includes today ($10) and 15d ago ($20) = $30.00 total.
        """
        response = get_profile(auth_client, "30d")
        html = response.data.decode()
        assert "30.00" in html, (
            "?period=30d total_spent should be $30.00 (today $10 + 15d $20)"
        )

    def test_total_spent_90d(self, auth_client):
        """
        90d window includes today ($10), 15d ($20), 60d ($40) = $70.00 total.
        """
        response = get_profile(auth_client, "90d")
        html = response.data.decode()
        assert "70.00" in html, (
            "?period=90d total_spent should be $70.00 (10 + 20 + 40)"
        )

    def test_total_spent_all(self, auth_client):
        """
        All-time: $10 + $20 + $40 + $80 = $150.00.
        """
        response = get_profile(auth_client, "all")
        html = response.data.decode()
        assert "150.00" in html, (
            "?period=all total_spent should be $150.00 (10 + 20 + 40 + 80)"
        )


# ===========================================================================
# 9. transaction_count reflects filter
# ===========================================================================

class TestTransactionCount:
    def test_transaction_count_30d_is_2(self, auth_client):
        response = get_profile(auth_client, "30d")
        html = response.data.decode()
        # 30d window: today + 15d ago = 2 transactions
        assert "2" in html, "transaction_count for 30d should be 2"

    def test_transaction_count_90d_is_3(self, auth_client):
        response = get_profile(auth_client, "90d")
        html = response.data.decode()
        # 90d window: today + 15d + 60d = 3 transactions
        assert "3" in html, "transaction_count for 90d should be 3"

    def test_transaction_count_all_is_4(self, auth_client):
        response = get_profile(auth_client, "all")
        html = response.data.decode()
        assert "4" in html, "transaction_count for all should be 4"

    def test_transaction_count_differs_between_month_and_all(self, auth_client):
        """
        The page body for 'all' must show 4; 'month' must show fewer than 4.
        """
        html_all = get_profile(auth_client, "all").data.decode()
        html_month = get_profile(auth_client, "month").data.decode()
        assert "4" in html_all, "all period must show count of 4"
        # Month cannot show 4 — it excludes 60d and 120d expenses
        # We simply assert all-time and month pages differ
        assert html_all != html_month, (
            "month and all period pages must differ in their reported data"
        )


# ===========================================================================
# 10. Category totals reflect filter
# ===========================================================================

class TestCategoryTotalsFilter:
    def test_period_month_no_bills_category(self, auth_client):
        """Bills expense is 60 days old — must not appear in month filter."""
        response = get_profile(auth_client, "month")
        html = response.data.decode()
        # Bills should not appear in the category breakdown for month
        assert "Bills" not in html, (
            "Bills category (60d old expense) must not appear in month filter"
        )

    def test_period_month_no_entertainment_category(self, auth_client):
        """Entertainment expense is 120 days old — must not appear in month filter."""
        response = get_profile(auth_client, "month")
        html = response.data.decode()
        assert "Entertainment" not in html, (
            "Entertainment category (120d old expense) must not appear in month filter"
        )

    def test_period_30d_no_bills_category(self, auth_client):
        """Bills expense is 60 days old — outside 30d window."""
        response = get_profile(auth_client, "30d")
        html = response.data.decode()
        assert "Bills" not in html, (
            "Bills category must not appear in 30d filter (expense is 60d old)"
        )

    def test_period_30d_no_entertainment_category(self, auth_client):
        """Entertainment expense is 120 days old — outside 30d window."""
        response = get_profile(auth_client, "30d")
        html = response.data.decode()
        assert "Entertainment" not in html, (
            "Entertainment must not appear in 30d filter (expense is 120d old)"
        )

    def test_period_90d_includes_bills_category(self, auth_client):
        """Bills expense is 60 days old — within 90d window."""
        response = get_profile(auth_client, "90d")
        html = response.data.decode()
        assert "Bills" in html, (
            "Bills category must appear in 90d filter (expense is 60d old)"
        )

    def test_period_90d_no_entertainment_category(self, auth_client):
        """Entertainment expense is 120 days old — outside 90d window."""
        response = get_profile(auth_client, "90d")
        html = response.data.decode()
        assert "Entertainment" not in html, (
            "Entertainment must not appear in 90d filter (expense is 120d old)"
        )

    def test_period_all_includes_all_categories(self, auth_client):
        """All four distinct categories must appear with ?period=all."""
        response = get_profile(auth_client, "all")
        html = response.data.decode()
        for cat in ("Food", "Transport", "Bills", "Entertainment"):
            assert cat in html, (
                f"Category '{cat}' must appear in ?period=all category breakdown"
            )

    def test_category_totals_differ_between_30d_and_all(self, auth_client):
        html_30d = get_profile(auth_client, "30d").data.decode()
        html_all = get_profile(auth_client, "all").data.decode()
        # Entertainment ($80) appears in all but not 30d
        assert "Entertainment" in html_all
        assert "Entertainment" not in html_30d


# ===========================================================================
# 11. Empty filtered period — no expenses in the selected range
# ===========================================================================

class TestEmptyFilteredPeriod:
    """
    Use a user with NO expenses to test the empty-state behavior for each period.
    """

    @pytest.fixture()
    def empty_auth_client(self, client, db_path):
        """A logged-in client whose account has zero expenses."""
        _seed_user(db_path, name="Empty User", email="empty@example.com",
                   password="emptypass")
        client.post(
            "/login",
            data={"email": "empty@example.com", "password": "emptypass"},
            follow_redirects=False,
        )
        return client

    @pytest.mark.parametrize("period", ["month", "30d", "90d", "all"])
    def test_empty_period_transaction_count_zero(self, empty_auth_client, period):
        response = get_profile(empty_auth_client, period)
        html = response.data.decode()
        assert response.status_code == 200, (
            f"?period={period} with no expenses must still return 200"
        )
        # When there are no transactions, the template shows the empty-hint
        assert "0" in html or "No transactions" in html, (
            f"?period={period} with no expenses must indicate zero transactions"
        )

    @pytest.mark.parametrize("period", ["month", "30d", "90d", "all"])
    def test_empty_period_shows_empty_hint(self, empty_auth_client, period):
        response = get_profile(empty_auth_client, period)
        html = response.data.decode()
        # The template shows this hint when transaction_count == 0
        assert "No transactions" in html, (
            f"?period={period} with no expenses must show 'No transactions' hint"
        )

    @pytest.mark.parametrize("period", ["month", "30d", "90d", "all"])
    def test_empty_period_filter_bar_still_rendered(self, empty_auth_client, period):
        response = get_profile(empty_auth_client, period)
        html = response.data.decode()
        assert "filter-bar" in html, (
            "filter-bar must still be rendered even when there are no transactions"
        )


# ===========================================================================
# 12. active_period variable drives correct active CSS class
# ===========================================================================

class TestActivePeriodClass:
    """
    For each valid period, only the corresponding button carries the 'active'
    class; the others do not.
    """

    @pytest.mark.parametrize("period,active_text,inactive_texts", [
        ("month", "This Month",    ["Last 30 Days", "Last 90 Days", "All Time"]),
        ("30d",   "Last 30 Days",  ["This Month",   "Last 90 Days", "All Time"]),
        ("90d",   "Last 90 Days",  ["This Month",   "Last 30 Days", "All Time"]),
        ("all",   "All Time",      ["This Month",   "Last 30 Days", "Last 90 Days"]),
    ])
    def test_active_class_on_correct_button(
        self, auth_client, period, active_text, inactive_texts
    ):
        response = get_profile(auth_client, period)
        html = response.data.decode()

        # Locate the active anchor — it must contain the expected label text
        # and carry the active class. We find the filter-btn active span.
        active_btn_start = html.find("filter-btn active")
        if active_btn_start == -1:
            # Try alternate ordering: "active filter-btn"
            active_btn_start = html.find("active\" href=")

        assert active_btn_start != -1, (
            f"?period={period} must produce exactly one active filter button"
        )

        # The active button text should appear near the active class marker
        # Grab a window of 200 chars around the active class
        window = html[max(0, active_btn_start - 20): active_btn_start + 200]
        assert active_text in window, (
            f"?period={period} — active button should contain text '{active_text}', "
            f"got window: {window!r}"
        )

    @pytest.mark.parametrize("period,active_param,inactive_param", [
        ("month", "month", ["30d", "90d", "all"]),
        ("30d",   "30d",   ["month", "90d", "all"]),
        ("90d",   "90d",   ["month", "30d", "all"]),
        ("all",   "all",   ["month", "30d", "90d"]),
    ])
    def test_only_one_filter_link_is_active(
        self, auth_client, period, active_param, inactive_param
    ):
        """Exactly one filter-btn must carry the active class per page load."""
        response = get_profile(auth_client, period)
        html = response.data.decode()
        # Count occurrences of "filter-btn active" in the HTML
        active_count = html.count("filter-btn active")
        assert active_count == 1, (
            f"?period={period} must have exactly one 'filter-btn active' element, "
            f"found {active_count}"
        )


# ===========================================================================
# 13. Filter bar always present with all four links
# ===========================================================================

class TestFilterBarRendering:
    @pytest.mark.parametrize("period", ["month", "30d", "90d", "all"])
    def test_filter_bar_contains_all_four_links(self, auth_client, period):
        response = get_profile(auth_client, period)
        html = response.data.decode()
        assert "?period=month" in html, "filter bar must always have ?period=month link"
        assert "?period=30d" in html,   "filter bar must always have ?period=30d link"
        assert "?period=90d" in html,   "filter bar must always have ?period=90d link"
        assert "?period=all" in html,   "filter bar must always have ?period=all link"

    @pytest.mark.parametrize("period", ["month", "30d", "90d", "all"])
    def test_filter_bar_button_labels(self, auth_client, period):
        response = get_profile(auth_client, period)
        html = response.data.decode()
        assert "This Month" in html,    "filter bar must always render 'This Month'"
        assert "Last 30 Days" in html,  "filter bar must always render 'Last 30 Days'"
        assert "Last 90 Days" in html,  "filter bar must always render 'Last 90 Days'"
        assert "All Time" in html,      "filter bar must always render 'All Time'"


# ===========================================================================
# 14. Template rendering — structural landmarks
# ===========================================================================

class TestTemplateRendering:
    def test_profile_page_has_stats_grid(self, auth_client):
        response = get_profile(auth_client)
        html = response.data.decode()
        assert "stats-grid" in html or "stat-card" in html, (
            "Profile page must render the stats grid"
        )

    def test_profile_page_shows_user_name(self, auth_client, seeded_db):
        response = get_profile(auth_client)
        html = response.data.decode()
        assert "Test User" in html, "Profile page must display the logged-in user's name"

    def test_profile_page_shows_user_email(self, auth_client, seeded_db):
        response = get_profile(auth_client)
        html = response.data.decode()
        assert "tester@example.com" in html, (
            "Profile page must display the logged-in user's email"
        )

    def test_profile_page_extends_base(self, auth_client):
        """Base template injects the page title — verify Spendly branding."""
        response = get_profile(auth_client)
        html = response.data.decode()
        assert "Spendly" in html, (
            "Profile page must extend base.html (Spendly appears in title/nav)"
        )
