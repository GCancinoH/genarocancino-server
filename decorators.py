from functools import wraps

from firebase_admin import auth
from flask import current_app, g, jsonify, request

from firebase_config import initialize_firebase

initialize_firebase()


def verify_firebase_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        authorization_header = request.headers.get("Authorization")
        if not authorization_header:
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        scheme, _, token = authorization_header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        try:
            decoded_token = auth.verify_id_token(token.strip(), check_revoked=True)
            g.user = decoded_token
            return f(*args, **kwargs)
        except auth.InvalidIdTokenError:
            return jsonify({"error": "Invalid ID token"}), 401
        except auth.ExpiredIdTokenError:
            return jsonify({"error": "Expired ID token"}), 401
        except auth.RevokedIdTokenError:
            return jsonify({"error": "Revoked ID token"}), 401
        except Exception:
            current_app.logger.exception("Firebase token verification failed")
            return jsonify({"error": "Token verification failed"}), 401

    return decorated_function


def require_role(required_role):
    """Decorator to require a specific role from Firebase custom claims."""
    def decorator(f):
        @wraps(f)
        @verify_firebase_token
        def decorated_function(*args, **kwargs):
            user = g.user
            if user.get("role") != required_role:
                return jsonify({"error": f"Insufficient permissions: requires {required_role} role"}), 403
            return f(*args, **kwargs)

        return decorated_function

    return decorator
