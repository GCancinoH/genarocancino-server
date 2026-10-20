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

    # Resend. La llave vive en RESEND_AKEY (el nombre elegido en Vercel) y se
    # acepta también RESEND_API_KEY, que es el que usa el SDK, por si la misma
    # configuración se reutiliza en otro entorno.
    RESEND_API_KEY = os.environ.get("RESEND_AKEY") or os.environ.get("RESEND_API_KEY")

    # Remitente. Resend solo acepta direcciones de un dominio verificado en
    # https://resend.com/domains. `onboarding@resend.dev` es la dirección de
    # prueba de Resend y SOLO entrega en `delivered@resend.dev`, o sea que no
    # sirve para mandarle credenciales a un paciente real: sirve para comprobar
    # que la integración funciona.
    RESEND_FROM = os.environ.get(
        "RESEND_FROM",
        "onboarding@resend.dev",
    )

    SECURITY_HEADERS_ENABLED = os.environ.get("SECURITY_HEADERS_ENABLED", "true").lower() == "true"
