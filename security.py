from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def configure_cors(app, allowed_origins):
    CORS(
        app,
        resources={r"/api/*": {"origins": allowed_origins}},
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Content-Type"],
        supports_credentials=False,
        max_age=600,
    )


def configure_security_headers(app):
    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        return response


def configure_rate_limits(app):
    return Limiter(
        key_func=get_remote_address,
        app=app,
        storage_uri=app.config.get("RATELIMIT_STORAGE_URI", "memory://"),
        strategy=app.config.get("RATELIMIT_STRATEGY", "moving-window"),
        default_limits=[],
    )
