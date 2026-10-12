import base64
import json
import os

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials

load_dotenv()

REQUIRED_FIREBASE_ENV_VARS = [
    "FIREBASE_PROJECT_ID",
    "FIREBASE_PRIVATE_KEY",
    "FIREBASE_CLIENT_EMAIL",
]


def _certificate_from_b64():
    """Service account completa codificada en base64 (recomendado en Vercel).

    Ventaja sobre las variables sueltas: no hay que partir la private key a
    mano ni escapar los saltos de línea. Se genera con:

        base64 -w 0 server/python-fb.json
    """
    encoded = os.environ.get("FIREBASE_SERVICE_ACCOUNT_B64")
    if not encoded:
        return None

    try:
        # Tolera que la variable venga con saltos de línea o espacios.
        service_account_info = json.loads(base64.b64decode(encoded).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_B64 no es un JSON válido en base64. "
            "Regenerala con: base64 -w 0 server/python-fb.json"
        ) from exc

    return credentials.Certificate(service_account_info)


def validate_firebase_env():
    missing = [name for name in REQUIRED_FIREBASE_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required Firebase environment variables: " + ", ".join(missing)
        )


def get_firebase_credentials():
    validate_firebase_env()

    raw_private_key = os.environ.get("FIREBASE_PRIVATE_KEY")
    private_key = raw_private_key.replace("\\n", "\n") if raw_private_key else None

    return {
        "type": "service_account",
        "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
        "private_key": private_key,
        "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": os.environ.get(
            "FIREBASE_CLIENT_X509_CERT_URL",
            "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40gc-nutrition.iam.gserviceaccount.com",
        ),
        "universe_domain": "googleapis.com",
    }


def initialize_firebase():
    if os.environ.get("SKIP_FIREBASE_INIT", "false").lower() == "true":
        return

    if not firebase_admin._apps:
        # Prioridad: service account completa en base64 > variables sueltas.
        cert = _certificate_from_b64()
        if cert is None:
            cert = credentials.Certificate(get_firebase_credentials())
        firebase_admin.initialize_app(cert)
