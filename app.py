import os
import secrets
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    DATABASE=os.environ.get(
        "DATABASE", str(Path(app.instance_path) / "expense_tracker.sqlite3")
    ),
    MAX_CONTENT_LENGTH=16 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
)

EXPENSE_CATEGORIES = (
    "Food",
    "Transport",
    "Housing",
    "Shopping",
    "Health",
    "Entertainment",
    "Bills",
    "Other",
)
INCOME_CATEGORIES = ("Salary", "Freelance", "Investment", "Gift", "Other")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db():
    database = get_db()
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            category TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            transaction_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS transactions_user_date
            ON transactions(user_id, transaction_date DESC, id DESC);
        """
    )
    database.commit()


@app.teardown_appcontext
def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


@app.before_request
def initialize_database():
    init_db()


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        supplied = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(supplied, expected):
            abort(400, description="The form expired. Please reload and try again.")


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'self'"
    )
    return response


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


@app.context_processor
def inject_template_values():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {
        "csrf_token": session["csrf_token"],
        "current_user_name": session.get("user_name"),
    }


@app.route("/")
@login_required
def dashboard():
    database = get_db()
    today = date.today()
    month = today.strftime("%Y-%m")
    totals = database.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN kind = 'income' THEN amount_cents END), 0)
                AS income_cents,
            COALESCE(SUM(CASE WHEN kind = 'expense' THEN amount_cents END), 0)
                AS expense_cents
        FROM transactions
        WHERE user_id = ? AND substr(transaction_date, 1, 7) = ?
        """,
        (session["user_id"], month),
    ).fetchone()
    transactions = database.execute(
        """
        SELECT id, kind, amount_cents, category, description, transaction_date
        FROM transactions
        WHERE user_id = ?
        ORDER BY transaction_date DESC, id DESC
        LIMIT 8
        """,
        (session["user_id"],),
    ).fetchall()
    return render_template(
        "dashboard.html",
        today=today.isoformat(),
        month_label=today.strftime("%B %Y"),
        income=Decimal(totals["income_cents"]) / 100,
        expenses=Decimal(totals["expense_cents"]) / 100,
        balance=Decimal(totals["income_cents"] - totals["expense_cents"]) / 100,
        transactions=[
            {**dict(item), "amount": Decimal(item["amount_cents"]) / 100}
            for item in transactions
        ],
        expense_categories=EXPENSE_CATEGORIES,
        income_categories=INCOME_CATEGORIES,
    )


@app.route("/register", methods=("GET", "POST"))
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or len(name) > 80:
            flash("Enter a name between 1 and 80 characters.", "error")
        elif len(email) > 254 or "@" not in email or any(c.isspace() for c in email):
            flash("Enter a valid email address.", "error")
        elif len(password) < 10 or len(password) > 128:
            flash("Your password must be between 10 and 128 characters.", "error")
        else:
            try:
                database = get_db()
                cursor = database.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (name, email, generate_password_hash(password)),
                )
                database.commit()
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "error")
            else:
                session.clear()
                session["user_id"] = cursor.lastrowid
                session["user_name"] = name
                session["csrf_token"] = secrets.token_urlsafe(32)
                return redirect(url_for("dashboard"))

    return render_template("auth.html", mode="register")


@app.route("/login", methods=("GET", "POST"))
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, name, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()

        if (
            user is None
            or len(password) > 128
            or not check_password_hash(user["password_hash"], password)
        ):
            flash("Email or password is incorrect.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("dashboard"))

    return render_template("auth.html", mode="login")


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.post("/transactions")
@login_required
def add_transaction():
    kind = request.form.get("kind", "")
    amount_text = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    date_text = request.form.get("transaction_date", "")
    allowed_categories = (
        INCOME_CATEGORIES if kind == "income" else EXPENSE_CATEGORIES
    )

    try:
        amount = Decimal(amount_text)
        transaction_date = date.fromisoformat(date_text)
    except (InvalidOperation, ValueError):
        flash("Enter a valid amount and date.", "error")
        return redirect(url_for("dashboard"))

    if kind not in ("income", "expense"):
        flash("Choose income or expense.", "error")
    elif not amount.is_finite() or amount <= 0 or amount > Decimal("999999999.99"):
        flash("Amount must be greater than zero and no more than 999,999,999.99.", "error")
    elif amount.as_tuple().exponent < -2:
        flash("Amounts can have at most two decimal places.", "error")
    elif category not in allowed_categories:
        flash("Choose a category from the list.", "error")
    elif len(description) > 120:
        flash("Description must be 120 characters or fewer.", "error")
    elif transaction_date > date.today():
        flash("Transaction date cannot be in the future.", "error")
    else:
        database = get_db()
        database.execute(
            """
            INSERT INTO transactions
                (user_id, kind, amount_cents, category, description, transaction_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                kind,
                int(amount * 100),
                category,
                description,
                transaction_date.isoformat(),
            ),
        )
        database.commit()
        flash("Transaction added.", "success")

    return redirect(url_for("dashboard"))


@app.post("/transactions/<int:transaction_id>/delete")
@login_required
def delete_transaction(transaction_id):
    database = get_db()
    cursor = database.execute(
        "DELETE FROM transactions WHERE id = ? AND user_id = ?",
        (transaction_id, session["user_id"]),
    )
    database.commit()
    if cursor.rowcount:
        flash("Transaction deleted.", "success")
    else:
        abort(404)
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
