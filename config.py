import os

from dotenv import load_dotenv

load_dotenv()


def _csv_env(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


class Config:
    ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    ALLOWED_ORIGINS = _csv_env(
        "ALLOWED_ORIGINS",
        "http://localhost:4200",
    )

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_USERNAME = os.environ.get("GOOGLE_MAIL") or os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("GOOGLE_MAIL_PASSWORD") or os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = (
        os.environ.get("MAIL_SENDER_NAME", "Sistema Ascenso"),
        MAIL_USERNAME,
    )

    SECURITY_HEADERS_ENABLED = os.environ.get("SECURITY_HEADERS_ENABLED", "true").lower() == "true"
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI") or "memory://"
    RATELIMIT_STRATEGY = os.environ.get("RATELIMIT_STRATEGY", "moving-window")
    PLAYER_CREATION_RATE_LIMIT = os.environ.get("PLAYER_CREATION_RATE_LIMIT", "10 per hour")
    PLAYERS_LIST_RATE_LIMIT = os.environ.get("PLAYERS_LIST_RATE_LIMIT", "60 per minute")
