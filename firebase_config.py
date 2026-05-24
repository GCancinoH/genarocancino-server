import os

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials

load_dotenv()


def get_firebase_credentials():
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
    if not firebase_admin._apps:
        cred = credentials.Certificate(get_firebase_credentials())
        firebase_admin.initialize_app(cred)
