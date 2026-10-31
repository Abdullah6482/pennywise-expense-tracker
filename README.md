# Pennywise

### Your money, in focus.

Pennywise is a clean, responsive expense tracker for keeping everyday income and spending in view. Create an account, record transactions, and see how this month is shaping up at a glance.

![Pennywise monthly dashboard overview](docs/screenshots/01-dashboard-overview.png)

<p align="center">
  <strong>Flask</strong> · <strong>SQLite</strong> · <strong>Python 3.10+</strong>
</p>

## What you can do

- **See your monthly snapshot** — income, expenses, and balance for the current month.
- **Keep a transaction log** — add income or expenses with a category, date, and optional note.
- **Review recent activity** — find your eight latest transactions and remove entries you no longer need.
- **Keep accounts separate** — registration and sign-in protect each user's transaction records.
- **Use it on any screen** — a responsive interface works across desktop and mobile.

## A look inside

| Monthly dashboard | Add an expense | Mobile layout |
|:--:|:--:|:--:|
| ![Monthly dashboard](docs/screenshots/01-dashboard-overview.png) | ![Expense entry form](docs/screenshots/05-expense-entry-form.png) | ![Responsive mobile dashboard](docs/screenshots/12-responsive-mobile.png) |

Browse the [complete screenshot gallery](docs/screenshots/README.md) for registration, sign-in, categories, transaction updates, and more.

## Run locally

**You’ll need** Python 3.10 or later.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). On first run, Pennywise creates its SQLite database at `instance/expense_tracker.sqlite3`.

To use another database location, set `DATABASE` before starting the app. If `SECRET_KEY` is not set, a temporary random key is generated at startup; sessions will expire when the process restarts. For a deployed instance, configure a persistent secret, use HTTPS, set `COOKIE_SECURE=1`, and run behind a production-ready WSGI server rather than Flask's development server.

## Run the tests

```powershell
python -m unittest discover -s tests
```

## Built with

- **[Flask](https://flask.palletsprojects.com/)** for the Python web application
- **SQLite** for persistent, per-user transaction storage
- **HTML, CSS, and vanilla JavaScript** for the responsive interface
- **Python's `unittest`** for the application test suite

## Security and data

Passwords are stored as hashes, form submissions use CSRF tokens, database queries are parameterized, and transaction deletion checks record ownership. SQLite data stays on the machine running the app; the repository does not include local databases or account data. Use fictional information when exploring the app, and do not expose a development instance to the public internet.

## Scope

Pennywise is a small, currency-neutral MVP. It provides a monthly summary and recent transactions; it does not yet include charts, exports, recurring transactions, a full transaction-history page, or multi-currency conversion.
