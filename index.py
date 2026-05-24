import datetime
import secrets
import string

from firebase_admin import auth, firestore
from flask import Flask, jsonify, render_template, request
from flask_mail import Mail, Message
from marshmallow import ValidationError

from config import Config
from decorators import require_role
from errors import error_response
from firebase_config import initialize_firebase
from security import configure_cors, configure_rate_limits, configure_security_headers
from validators import validate_player_creation_payload

app = Flask(__name__)
app.config.from_object(Config)

configure_cors(app, app.config["ALLOWED_ORIGINS"])
if app.config["SECURITY_HEADERS_ENABLED"]:
    configure_security_headers(app)
limiter = configure_rate_limits(app)

mail = Mail(app)

initialize_firebase()


def generate_player_password():
    alphabet = string.ascii_letters + string.digits + "!@#$"
    return "Player@" + "".join(secrets.choice(alphabet) for _ in range(8))


def send_new_player_email(email, display_name, password, premium_until_timestamp):
    """Send the player their temporary password.

    The admin explicitly wants players to receive a password so they can enter
    the system. Keep this email, but do not return the password in API JSON.
    """
    premium_until = datetime.datetime.fromtimestamp(premium_until_timestamp).strftime('%d/%m/%Y')
    html = render_template(
        'new_player_email.html',
        display_name=display_name or 'Jugador(a)',
        email=email,
        password=password,
        premium_until=premium_until,
    )
    text = f"""NOTIFICACIÓN DEL SISTEMA

Has sido seleccionado(a) por el sistema para evolucionar de una forma sin precedentes.

Credenciales
Email: {email}
Contraseña: {password}

Tu acceso premium inicial estará activo hasta: {premium_until}

Ingresa al sistema y cambia tu contraseña lo antes posible.
"""

    message = Message(
        subject='NOTIFICACIÓN DEL SISTEMA | Acceso Ascenso',
        recipients=[email],
        body=text,
        html=html,
    )
    mail.send(message)


@app.route('/api/health')
def health():
    return jsonify({"status": "ok"}), 200


@app.route('/home')
def home():
    return jsonify({"status": "ok"}), 200


@app.route('/')
def hello_world():
    return jsonify({"status": "ok"}), 200


@app.route("/api/v1/players", methods=["GET"])
@limiter.limit(lambda: app.config["PLAYERS_LIST_RATE_LIMIT"])
@require_role("admin")
def list_players():
    try:
        players = []
        page = auth.list_users()
        while page:
            for user in page.users:
                claims = user.custom_claims or {}
                if claims.get('role') == 'player':
                    players.append({
                        "uid": user.uid,
                        "displayName": user.display_name,
                        "email": user.email,
                        "customClaims": claims,
                        "disabled": user.disabled,
                    })
            page = page.get_next_page()

        return jsonify(players), 200
    except Exception:
        app.logger.exception("Unexpected error while listing players")
        return error_response("Internal server error", 500)


@app.route("/api/v1/player-creation", methods=["POST"])
@limiter.limit(lambda: app.config["PLAYER_CREATION_RATE_LIMIT"])
@require_role("admin")
def player_creation():
    try:
        data = validate_player_creation_payload(request.get_json(silent=True))
    except ValidationError as validation_error:
        return error_response("Invalid request", 400, validation_error.messages)

    email = data["email"]
    display_name = data["displayName"]
    age = data["age"]

    now = datetime.datetime.now()
    expiration_date = now + datetime.timedelta(days=30)
    premium_until_timestamp = int(expiration_date.timestamp())
    password = generate_player_password()

    try:
        user = auth.create_user(
            email=email,
            password=password,
            display_name=display_name,
        )

        auth.set_custom_user_claims(user.uid, {
            'role': 'player',
            'premiumAccount': True,
            'premiumUntil': premium_until_timestamp,
        })

        db = firestore.client()
        db.collection('players').document(user.uid).set({
            'displayName': display_name,
            'email': email,
            'age': age,
        })

        db.collection('player_rewards').document(user.uid).set({
            'xp': 0,
            'level': 1,
            'coins': 0,
        })

        email_sent = True
        email_error = None
        try:
            send_new_player_email(email, display_name, password, premium_until_timestamp)
        except Exception:
            email_sent = False
            email_error = "Failed to send welcome email"
            app.logger.exception("Error sending player welcome email")

        response = {
            "message": "Player created successfully",
            "uid": user.uid,
            "email": user.email,
            "displayName": display_name,
            "emailSent": email_sent,
        }
        if email_error:
            response["emailError"] = email_error

        return jsonify(response), 201

    except auth.EmailAlreadyExistsError:
        return error_response("A user with this email already exists", 400)
    except Exception:
        app.logger.exception("Unexpected error while creating player")
        return error_response("Internal server error", 500)


if __name__ == '__main__':
    app.run(debug=app.config["DEBUG"])
