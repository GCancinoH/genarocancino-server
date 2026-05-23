import os
import firebase_admin
from firebase_admin import credentials, auth
from flask import g, request, jsonify
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

# Initialize Firebase Admin (once)
if not firebase_admin._apps:
    firebase_credentials_path = os.getenv(
        "FIREBASE_SERVICE_ACCOUNT_PATH",
        os.path.join(os.path.dirname(__file__), "python-fb.json")
    )
    cred = credentials.Certificate(firebase_credentials_path)
    firebase_admin.initialize_app(cred)
    
def verify_firebase_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        id_token = request.headers.get("Authorization")
        if not id_token or not id_token.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
            
        id_token = id_token.split("Bearer ")[1]
            
        try:
            # Verifies signature, expiry, and revocation
            decoded_token = auth.verify_id_token(id_token, check_revoked=True)
            g.user = decoded_token  # Attach to Flask context for route access
            return f(*args, **kwargs)
        except auth.InvalidIdTokenError:
            return jsonify({"error": "Invalid ID token"}), 401
        except auth.ExpiredIdTokenError:
            return jsonify({"error": "Expired ID token"}), 401
        except auth.RevokedIdTokenError:
            return jsonify({"error": "Revoked ID token"}), 401
        except Exception as e:
            return jsonify({"error": f"Token verification failed: {str(e)}"}), 401
    return decorated_function
    
def require_role(required_role):
    """Decorator to require specific role from custom claims"""
    def decorator(f):
        @wraps(f)
        @verify_firebase_token  # Must verify token first
        def decorated_function(*args, **kwargs):
            user = g.user
            # Check custom claims (set via Admin SDK)
            if user.get("role") != required_role:
                return jsonify({"error": f"Insufficient permissions: requires {required_role} role"}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator