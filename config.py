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

    # ------------------------------------------------------------------
    # Correo por SMTP de Brevo
    # ------------------------------------------------------------------
    #
    # Servidor, puerto y usuario de acceso NO son secretos: son datos
    # públicos de Brevo. El usuario es un identificador de cuenta, inútil
    # sin la contraseña. Se dejan fijos para que lo único que haya que
    # tocar en Vercel sea la llave.
    MAIL_SERVER = "smtp-relay.brevo.com"
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = True
    MAIL_USERNAME = "88b372001@smtp-brevo.com"

    # El ÚNICO secreto del transporte. Vive en Vercel; no se sube a git.
    MAIL_PASSWORD = os.environ.get("BREVO_KEY")

    # Remitente que ve el paciente. Ojo: NO es lo mismo que MAIL_USERNAME.
    # Brevo exige que esta dirección esté dada de alta en
    # https://app.brevo.com/settings/senders/emails y verificada con el
    # código que manda al propio buzón. Si no está, el envío se rechaza
    # y el paciente no recibe nada.
    MAIL_SENDER = os.environ.get("MAIL_SENDER", "genarocancinonutricion@gmail.com")
    MAIL_SENDER_NAME = os.environ.get("MAIL_SENDER_NAME", "Nutrición Ascenso")

    MAIL_DEFAULT_SENDER = (MAIL_SENDER_NAME, MAIL_SENDER)

    SECURITY_HEADERS_ENABLED = os.environ.get("SECURITY_HEADERS_ENABLED", "true").lower() == "true"
