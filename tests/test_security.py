import os
import sys
from pathlib import Path

from flask import Flask, jsonify

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["SKIP_FIREBASE_INIT"] = "true"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:4200,https://app.example"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"

import index  # noqa: E402
from security import configure_rate_limits  # noqa: E402


class DummyDocument:
    def set(self, data):
        self.data = data


class DummyCollection:
    def document(self, uid):
        return DummyDocument()


class DummyFirestoreClient:
    def collection(self, name):
        return DummyCollection()


class DummyUser:
    uid = "user-123"
    email = "player@example.com"


def authenticate_as_admin(monkeypatch):
    monkeypatch.setattr(
        "decorators.auth.verify_id_token",
        lambda token, check_revoked=True: {"uid": "admin-1", "role": "admin"},
    )


def test_allowed_cors_origin_receives_allow_origin_header():
    client = index.app.test_client()

    response = client.options(
        "/api/v1/players",
        headers={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )

    assert response.headers.get("Access-Control-Allow-Origin") == "http://localhost:4200"


def test_disallowed_cors_origin_does_not_receive_allow_origin_header():
    client = index.app.test_client()

    response = client.options(
        "/api/v1/players",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers.get("Access-Control-Allow-Origin") is None


def test_security_headers_are_added_to_health_response():
    client = index.app.test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "no-referrer"


def test_missing_authorization_header_returns_401():
    client = index.app.test_client()

    response = client.get("/api/v1/players")

    assert response.status_code == 401
    assert response.get_json() == {"error": "Missing or invalid Authorization header"}


def test_wrong_authorization_scheme_returns_401():
    client = index.app.test_client()

    response = client.get("/api/v1/players", headers={"Authorization": "Token abc"})

    assert response.status_code == 401
    assert response.get_json() == {"error": "Missing or invalid Authorization header"}


def test_invalid_player_creation_payload_returns_400(monkeypatch):
    authenticate_as_admin(monkeypatch)
    client = index.app.test_client()

    response = client.post(
        "/api/v1/player-creation",
        json={"email": "not-email", "displayName": "", "age": 999},
        headers={"Authorization": "Bearer valid-admin-token"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "Invalid request"
    assert "details" in payload


def test_flask_limiter_uses_configured_storage_uri_and_enforces_limits():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["RATELIMIT_STORAGE_URI"] = "memory://"
    app.config["RATELIMIT_STRATEGY"] = "fixed-window"
    limiter = configure_rate_limits(app)

    @app.route("/api/test-rate-limit")
    @limiter.limit("1 per minute")
    def test_rate_limit_route():
        return jsonify({"status": "ok"}), 200

    client = app.test_client()

    first_response = client.get("/api/test-rate-limit")
    second_response = client.get("/api/test-rate-limit")

    assert first_response.status_code == 200
    assert second_response.status_code == 429


def test_player_creation_does_not_return_password_but_still_emails_it(monkeypatch):
    authenticate_as_admin(monkeypatch)
    monkeypatch.setattr(index.auth, "create_user", lambda **kwargs: DummyUser())
    monkeypatch.setattr(index.auth, "set_custom_user_claims", lambda uid, claims: None)
    monkeypatch.setattr(index.firestore, "client", lambda: DummyFirestoreClient())

    sent_email_args = {}

    def fake_send_new_player_email(email, display_name, password, premium_until_timestamp):
        sent_email_args.update(
            {
                "email": email,
                "display_name": display_name,
                "password": password,
                "premium_until_timestamp": premium_until_timestamp,
            }
        )

    monkeypatch.setattr(index, "send_new_player_email", fake_send_new_player_email)
    client = index.app.test_client()

    response = client.post(
        "/api/v1/player-creation",
        json={"email": "player@example.com", "displayName": "Player One", "age": 20},
        headers={"Authorization": "Bearer valid-admin-token"},
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert "password" not in payload
    assert payload["emailSent"] is True
    assert sent_email_args["password"].startswith("Player@")
