import os
import sys
from pathlib import Path

import pytest
from resend.exceptions import ResendError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["SKIP_FIREBASE_INIT"] = "true"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:4200,https://app.example"

import index  # noqa: E402


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


def test_player_deletion_requires_admin(monkeypatch):
    client = index.app.test_client()

    response = client.post("/api/v1/player-deletion", json={"uid": "user-123"})

    assert response.status_code == 401


def test_player_deletion_rejects_payload_without_uid(monkeypatch):
    authenticate_as_admin(monkeypatch)
    client = index.app.test_client()

    response = client.post(
        "/api/v1/player-deletion",
        json={},
        headers={"Authorization": "Bearer valid-admin-token"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "Invalid request"
    assert "details" in payload


def test_player_deletion_deletes_auth_account_and_returns_no_password(monkeypatch):
    authenticate_as_admin(monkeypatch)
    deleted_uids = []

    monkeypatch.setattr(
        index.auth,
        "delete_user",
        lambda uid: deleted_uids.append(uid),
    )
    client = index.app.test_client()

    response = client.post(
        "/api/v1/player-deletion",
        json={"uid": "user-123"},
        headers={"Authorization": "Bearer valid-admin-token"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["uid"] == "user-123"
    assert "password" not in payload
    assert deleted_uids == ["user-123"]


def test_player_deletion_is_idempotent_when_account_is_already_gone(monkeypatch):
    authenticate_as_admin(monkeypatch)

    def raise_not_found(uid):
        raise index.auth.UserNotFoundError("User not found")

    monkeypatch.setattr(index.auth, "delete_user", raise_not_found)
    client = index.app.test_client()

    response = client.post(
        "/api/v1/player-deletion",
        json={"uid": "already-gone"},
        headers={"Authorization": "Bearer valid-admin-token"},
    )

    # Un reintento tras un borrado parcial no debe fallar por "no existe".
    assert response.status_code == 200
    assert response.get_json()["uid"] == "already-gone"


def test_player_deletion_returns_500_on_unexpected_auth_error(monkeypatch):
    authenticate_as_admin(monkeypatch)

    def raise_runtime_error(uid):
        raise RuntimeError("boom")

    monkeypatch.setattr(index.auth, "delete_user", raise_runtime_error)
    client = index.app.test_client()

    response = client.post(
        "/api/v1/player-deletion",
        json={"uid": "user-123"},
        headers={"Authorization": "Bearer valid-admin-token"},
    )

    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}


# ---------------------------------------------------------------------------
# Correo de bienvenida por Resend
# ---------------------------------------------------------------------------

def test_health_reports_mail_configuration_without_exposing_the_key():
    client = index.app.test_client()

    response = client.get("/api/health")
    payload = response.get_json()

    assert response.status_code == 200
    # Sin la variable de entorno, no hay con qué enviar.
    assert payload["mailConfigured"] is False
    assert payload["mailFrom"] == "onboarding@resend.dev"
    assert payload["mailIsTestAddress"] is True
    # El diagnóstico no debe filtrar la llave ni nada parecido.
    assert "key" not in payload
    assert "RESEND" not in payload


def test_health_reports_configured_sender_once_the_key_is_present(monkeypatch):
    monkeypatch.setitem(index.app.config, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setitem(
        index.app.config, "RESEND_FROM", "Nutricion <hola@dominio-verificado.com>"
    )
    client = index.app.test_client()

    payload = client.get("/api/health").get_json()

    assert payload["mailConfigured"] is True
    assert payload["mailFrom"] == "Nutricion <hola@dominio-verificado.com>"
    assert payload["mailIsTestAddress"] is False


def test_send_welcome_email_fails_loudly_when_the_key_is_missing(monkeypatch):
    monkeypatch.setitem(index.app.config, "RESEND_API_KEY", None)

    # Que reviente aqui y no devuelva un exito silencioso: el llamador
    # convierte la excepcion en emailSent: false, que es lo que se quiere.
    with pytest.raises(RuntimeError, match="RESEND_AKEY"):
        index.send_new_player_email("player@example.com", "Player One", "Player@1234", 0)


def test_send_welcome_email_goes_through_resend_with_the_right_payload(monkeypatch):
    monkeypatch.setitem(index.app.config, "RESEND_API_KEY", "re_test_key")
    monkeypatch.setitem(index.app.config, "RESEND_FROM", "Nutricion <hola@dominio.com>")

    sent = []
    monkeypatch.setattr(
        index.resend.Emails,
        "send",
        lambda params: sent.append(params) or {"id": "msg-1"},
    )

    # render_template necesita contexto de aplicación para encontrar la
    # plantilla, así que se llama dentro de uno.
    with index.app.app_context():
        index.send_new_player_email(
            "player@example.com", "Player One", "Player@1234", 1700000000
        )

    assert len(sent) == 1
    params = sent[0]
    assert params["from"] == "Nutricion <hola@dominio.com>"
    assert params["to"] == ["player@example.com"]
    assert "NOTIFICACIÓN DEL SISTEMA" in params["subject"]
    # El password va en el correo, que es el unico sitio donde debe ir.
    assert "Player@1234" in params["text"]
    assert "Player@1234" in params["html"]
    assert "player@example.com" in params["html"]


def test_resend_failure_is_reported_as_email_not_sent(monkeypatch):
    authenticate_as_admin(monkeypatch)
    monkeypatch.setattr(index.auth, "create_user", lambda **kwargs: DummyUser())
    monkeypatch.setattr(index.auth, "set_custom_user_claims", lambda uid, claims: None)
    monkeypatch.setattr(index.firestore, "client", lambda: DummyFirestoreClient())
    monkeypatch.setitem(index.app.config, "RESEND_API_KEY", "re_test_key")

    def boom(params):
        raise ResendError(
            code=422,
            error_type="validation_error",
            message="The from address is not verified",
            suggested_action="Verifica el dominio en resend.com/domains",
        )

    monkeypatch.setattr(index.resend.Emails, "send", boom)
    client = index.app.test_client()

    response = client.post(
        "/api/v1/player-creation",
        json={"email": "player@example.com", "displayName": "Player One", "age": 20},
        headers={"Authorization": "Bearer valid-admin-token"},
    )

    # La cuenta SI se crea; solo falla el correo, y eso se avisa en la
    # respuesta para que el nutriologo pueda entregar las credenciales a mano.
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["emailSent"] is False
    assert payload["emailError"] == "Failed to send welcome email"
    assert "password" not in payload
