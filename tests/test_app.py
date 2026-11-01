import os
import re
import sqlite3
import tempfile
import unittest

from app import app, deployment_config, init_db


class ExpenseTrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            DATABASE=os.path.join(self.temp_dir.name, "test.sqlite3"),
        )
        with app.app_context():
            init_db()
        self.client = app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def csrf_token(self, response):
        match = re.search(
            rb'name="csrf_token" value="([^"]+)"', response.data
        )
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def test_production_requires_a_persistent_secret_key(self):
        for secret_key in ("", "too-short"):
            with self.subTest(secret_key=secret_key):
                with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                    deployment_config(
                        {"APP_ENV": "production", "SECRET_KEY": secret_key}
                    )

    def test_production_enables_secure_cookies_and_configured_proxy_trust(self):
        config = deployment_config(
            {
                "APP_ENV": "production",
                "SECRET_KEY": "p" * 64,
                "TRUSTED_PROXY_HOPS": "1",
            }
        )
        self.assertTrue(config["SESSION_COOKIE_SECURE"])
        self.assertEqual(config["TRUSTED_PROXY_HOPS"], 1)

        original_secure_setting = app.config["SESSION_COOKIE_SECURE"]
        self.addCleanup(
            app.config.__setitem__,
            "SESSION_COOKIE_SECURE",
            original_secure_setting,
        )
        app.config["SESSION_COOKIE_SECURE"] = config["SESSION_COOKIE_SECURE"]
        response = self.client.get("/register")
        self.assertIn("; Secure", response.headers.get("Set-Cookie", ""))

    def test_development_cookie_setting_and_proxy_configuration_are_explicit(self):
        development = deployment_config({"APP_ENV": "development"})
        self.assertFalse(development["SESSION_COOKIE_SECURE"])
        with self.assertRaisesRegex(ValueError, "TRUSTED_PROXY_HOPS"):
            deployment_config(
                {"APP_ENV": "development", "TRUSTED_PROXY_HOPS": "-1"}
            )
        with self.assertRaisesRegex(RuntimeError, "cannot be disabled"):
            deployment_config(
                {
                    "APP_ENV": "production",
                    "SECRET_KEY": "p" * 64,
                    "COOKIE_SECURE": "0",
                }
            )

    def register(self):
        response = self.client.get("/register")
        token = self.csrf_token(response)
        return self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "name": "Alex",
                "email": "alex@example.com",
                "password": "a-strong-password",
            },
            follow_redirects=True,
        )

    def test_registration_adds_transaction_and_updates_summary(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Small steps", response.data)

        token = self.csrf_token(response)
        added = self.client.post(
            "/transactions",
            data={
                "csrf_token": token,
                "kind": "expense",
                "amount": "12.50",
                "category": "Food",
                "description": "Lunch",
                "transaction_date": "2026-10-12",
            },
            follow_redirects=True,
        )
        self.assertEqual(added.status_code, 200)
        self.assertIn(b"12.50", added.data)
        self.assertIn(b"Lunch", added.data)

    def test_dashboard_requires_login_and_post_requires_csrf(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        response = self.client.get("/register")
        rejected = self.client.post(
            "/register",
            data={
                "name": "Alex",
                "email": "alex@example.com",
                "password": "a-strong-password",
            },
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(response.status_code, 200)

    def test_registered_user_can_sign_in(self):
        self.register()
        token = self.csrf_token(self.client.get("/"))
        self.client.post("/logout", data={"csrf_token": token})
        response = self.client.get("/login")
        signed_in = self.client.post(
            "/login",
            data={
                "csrf_token": self.csrf_token(response),
                "email": "ALEX@example.com",
                "password": "a-strong-password",
            },
            follow_redirects=True,
        )
        self.assertEqual(signed_in.status_code, 200)
        self.assertIn(b"Small steps", signed_in.data)

    def test_user_cannot_delete_another_users_transaction(self):
        self.register()
        token = self.csrf_token(self.client.get("/"))
        self.client.post(
            "/transactions",
            data={
                "csrf_token": token,
                "kind": "income",
                "amount": "100",
                "category": "Salary",
                "description": "Pay",
                "transaction_date": "2026-10-12",
            },
        )
        with app.app_context():
            connection = sqlite3.connect(app.config["DATABASE"])
            connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Taylor", "taylor@example.com", "unused"),
            )
            second_user_id = connection.execute(
                "SELECT id FROM users WHERE email = ?", ("taylor@example.com",)
            ).fetchone()[0]
            transaction_id = connection.execute(
                "SELECT id FROM transactions"
            ).fetchone()[0]
            connection.commit()
            connection.close()

        with self.client.session_transaction() as browser_session:
            browser_session.clear()
            browser_session["user_id"] = second_user_id
            browser_session["user_name"] = "Taylor"
            browser_session["csrf_token"] = "second-user-token"
        response = self.client.post(
            f"/transactions/{transaction_id}/delete",
            data={"csrf_token": "second-user-token"},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
