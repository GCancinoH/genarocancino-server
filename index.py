#from server.decorators import require_role
import datetime
import os
import secrets
import string
from flask import Flask, request, jsonify, render_template
from flask_mail import Mail, Message
import firebase_admin
from firebase_admin import auth, credentials, firestore
from dotenv import load_dotenv
from decorators import require_role

load_dotenv()

app = Flask(__name__)
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS='true',
    MAIL_USE_SSL='true',
    MAIL_USERNAME=os.environ.get('GOOGLE_MAIL'),
    MAIL_PASSWORD=os.environ.get('GOOGLE_MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=(
        os.environ.get('MAIL_SENDER_NAME', 'Sistema Ascenso'),
        os.environ.get('GOOGLE_MAIL')
    ),
)

mail = Mail(app)

# Firebase Config
raw_private_key = os.environ.get("FIREBASE_PRIVATE_KEY")
if raw_private_key:
    # This ensures Python treats '\n' as an actual newline character
    private_key = raw_private_key.replace("\\n", "\n")
else:
    private_key = None

if not firebase_admin._apps:
    cred = credentials.Certificate({
        "type": "service_account",
        "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
        "private_key": private_key,
        "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40gc-nutrition.iam.gserviceaccount.com",
        "universe_domain": "googleapis.com"
    })
    firebase_admin.initialize_app(cred)


def send_new_player_email(email, display_name, password, premium_until_timestamp):
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

@app.before_request
def before_request():
    if request.method == "OPTIONS":
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response, 200

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/')
def hello_world():
    return 'Hello, World!'

@app.route("/api/v1/players", methods=["GET"])
@require_role("admin")
def list_players():
    try:
        players = []
        # List users in pages
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
                        "disabled": user.disabled
                    })
            page = page.get_next_page()
            
        return jsonify(players), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/v1/player-creation", methods=["POST"])
@require_role("admin")
def player_creation():
    data = request.get_json()
    # Calculate premium expiration (30 days from now)
    now = datetime.datetime.now()
    expiration_date = now + datetime.timedelta(days=30)
    premium_until_timestamp = int(expiration_date.timestamp())
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    email = data.get('email')
    display_name = data.get('displayName')
    age = data.get('edad') or data.get('age') or 18
    
    if not email:
        return jsonify({"error": "Email is required"}), 400
        
    # Generate secure temporary password
    alphabet = string.ascii_letters + string.digits + "!@#$"
    password = "Player@" + "".join(secrets.choice(alphabet) for _ in range(8))
        
    try:
        # Create the user in Firebase Auth
        user = auth.create_user(
            email=email,
            password=password,
            display_name=display_name
        )
        
        # Set custom claims
        auth.set_custom_user_claims(user.uid, {
            'role': 'player',
            'premiumAccount': True,
            'premiumUntil': premium_until_timestamp
        })
        
        # Write to Firestore
        db = firestore.client()
        
        # 1. Save player profile document
        db.collection('players').document(user.uid).set({
            'displayName': display_name,
            'email': email,
            'age': int(age),
        })
        
        # 2. Initialize player rewards document
        db.collection('player_rewards').document(user.uid).set({
            'xp': 0,
            'level': 1,
            'coins': 0
        })

        email_sent = True
        email_error = None
        try:
            send_new_player_email(email, display_name, password, premium_until_timestamp)
        except Exception as mail_error:
            email_sent = False
            email_error = str(mail_error)
            print(f"Error sending player welcome email: {mail_error}")
        
        response = {
            "message": "Player created successfully",
            "uid": user.uid,
            "email": user.email,
            "displayName": display_name,
            "password": password,
            "emailSent": email_sent
        }
        if email_error:
            response["emailError"] = email_error

        return jsonify(response), 201
        
    except auth.EmailAlreadyExistsError:
        return jsonify({"error": "A user with this email already exists"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)