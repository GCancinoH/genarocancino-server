import functools
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


_RATE_LIMIT_WINDOWS = {
    "second": 1,
    "seconds": 1,
    "minute": 60,
    "minutes": 60,
    "hour": 60 * 60,
    "hours": 60 * 60,
    "day": 24 * 60 * 60,
    "days": 24 * 60 * 60,
}


class UpstashRedisRateLimiter:
    """Small fixed-window limiter backed by Upstash Redis REST.

    Flask-Limiter's Redis storage expects a Redis TCP URL. Vercel's Upstash
    integration commonly exposes REST credentials instead, so this adapter uses
    UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN directly while preserving
    the existing @limiter.limit("N per unit") decorator shape used by index.py.
    """

    def __init__(self, rest_url, rest_token, key_prefix="flask-rate-limit", fail_open=True):
        self.rest_url = rest_url.rstrip("/")
        self.rest_token = rest_token
        self.key_prefix = key_prefix.strip(":") or "flask-rate-limit"
        self.fail_open = fail_open

    def limit(self, limit_value):
        def decorator(view_func):
            @functools.wraps(view_func)
            def wrapper(*args, **kwargs):
                if request.method == "OPTIONS":
                    return view_func(*args, **kwargs)

                raw_limit = limit_value() if callable(limit_value) else limit_value
                max_requests, window_seconds = parse_rate_limit(raw_limit)
                if not self._is_allowed(max_requests, window_seconds, raw_limit):
                    response = jsonify({"error": "Rate limit exceeded"})
                    response.status_code = 429
                    response.headers["Retry-After"] = str(window_seconds)
                    return response

                return view_func(*args, **kwargs)

            return wrapper

        return decorator

    def _is_allowed(self, max_requests, window_seconds, raw_limit):
        identity = get_remote_address() or "unknown"
        endpoint = request.endpoint or request.path
        bucket = int(time.time() // window_seconds)
        key = f"{self.key_prefix}:{endpoint}:{identity}:{raw_limit}:{bucket}"

        try:
            current_count = self._increment_window(key, window_seconds)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError):
            if self.fail_open:
                return True
            raise

        return current_count <= max_requests

    def _increment_window(self, key, window_seconds):
        payload = json.dumps(
            [
                ["INCR", key],
                ["EXPIRE", key, str(window_seconds + 5), "NX"],
            ]
        ).encode("utf-8")
        req = Request(
            f"{self.rest_url}/pipeline",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.rest_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlopen(req, timeout=3) as response:
            body = json.loads(response.read().decode("utf-8"))

        first_result = body[0]
        if "error" in first_result:
            raise ValueError(first_result["error"])
        return int(first_result["result"])


def parse_rate_limit(limit_value):
    """Parse Flask-Limiter style strings like '10 per hour'."""
    parts = str(limit_value).strip().lower().split()
    if len(parts) != 3 or parts[1] not in {"per", "/"}:
        raise ValueError(f"Unsupported rate limit format: {limit_value!r}")

    max_requests = int(parts[0])
    window_seconds = _RATE_LIMIT_WINDOWS[parts[2]]
    return max_requests, window_seconds


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
    upstash_rest_url = app.config.get("UPSTASH_REDIS_REST_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    upstash_rest_token = app.config.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")

    if upstash_rest_url and upstash_rest_token:
        return UpstashRedisRateLimiter(
            rest_url=upstash_rest_url,
            rest_token=upstash_rest_token,
            key_prefix=app.config.get("RATELIMIT_KEY_PREFIX", "flask-rate-limit"),
            fail_open=app.config.get("RATELIMIT_FAIL_OPEN", True),
        )

    return Limiter(
        key_func=get_remote_address,
        app=app,
        storage_uri=app.config.get("RATELIMIT_STORAGE_URI", "memory://"),
        default_limits=[],
    )
