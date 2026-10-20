"""
Crea una cuenta en Firebase Auth y, si se pide, le otorga el rol admin.

Es el complemento de `set_admin_role.py`: ese asume que el usuario ya
existe y solo toca el claim; este crea la cuenta de cero y el claim en el
mismo paso.

Corre en local contra la service account. No hay endpoint público ni
contraseña compartida en el código: la única llave es el archivo de
service account, que no se sube a git. Para crear el PRIMER admin de un
proyecto —o para recuperarse cuando a uno se le borra la propia cuenta—
hace falta exactamente ese arranque desde fuera del flujo de tokens.

Uso:
    python create_user.py tu@correo.com --admin
    python create_user.py paciente@correo.com --name "Ana López"
    python create_user.py paciente@correo.com --password "MiClave123"
    python create_user.py paciente@correo.com --dry-run

Si el correo ya existe no falla: reutiliza la cuenta y solo añade el rol
si se pidió. Así sirve también para dar admin a alguien que ya estabas
usando.

El rol vive en el custom claim `role`, la MISMA fuente de verdad que usan
adminGuard (UI), decorators.require_role (backend) y firestore.rules.

NOTA: los claims viven en el ID token. Después de correrlo, cierra sesión
y vuelve a entrar en la app (o espera ~1 h) para que el token se refresque.
"""

import argparse
import os
import secrets
import string
import sys

import firebase_admin
from firebase_admin import auth, credentials

# --- Configuración ---------------------------------------------------------

PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "gc-nutrition")

# Ruta a la service account. Prioriza la variable de entorno y si no,
# usa la que está junto a este script. Es la misma resolución que usa
# set_admin_role.py, para que los dos scripts se comporten igual.
_CANDIDATE_PATHS = [
    os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH"),
    os.path.join(os.path.dirname(__file__), "python-fb.json"),
]

SERVICE_ACCOUNT_PATH = next(
    (p for p in _CANDIDATE_PATHS if p and os.path.exists(p)), None
)

if not SERVICE_ACCOUNT_PATH:
    sys.exit(
        "No se encontró la service account. Define FIREBASE_SERVICE_ACCOUNT_PATH "
        "o coloca python-fb.json junto a este script."
    )


def _init_app():
    """Inicializa el Admin SDK una sola vez."""
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})


def generate_password() -> str:
    """Genera un password temporal con el mismo formato que el backend.

    `Player@` + 10 caracteres. El prefijo hace reconocible el correo de
    bienvenida y evita que se confunda con una clave que el paciente
    eligiera él mismo.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$"
    return "Player@" + "".join(secrets.choice(alphabet) for _ in range(10))


def create_user(
    email: str,
    password: str | None = None,
    display_name: str | None = None,
    make_admin: bool = False,
    dry_run: bool = False,
) -> int:
    """Crea (o reutiliza) la cuenta y le asigna el rol si se pide.

    Devuelve el código de salida: 0 todo bien, 1 algo falló.
    """
    _init_app()

    if "@" not in email:
        print(f"✗ «{email}» no parece un correo válido.")
        return 1

    # Estado actual, en solo lectura. Se consulta ANTES de decidir nada, y
    # sirve tanto para el --dry-run como para no intentar crear encima de
    # una cuenta que ya existe.
    try:
        existing = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        existing = None

    if dry_run:
        claims_preview = dict(existing.custom_claims or {}) if existing else {}
        print("─" * 60)
        print("MODO PRUEBA: no se escribió nada.")
        print(f"  Correo           : {email}")
        print(f"  ¿Ya existe?      : {'sí' if existing else 'no'}")
        if existing:
            print(f"  ¿Deshabilitada?  : {'sí' if existing.disabled else 'no'}")
            print(f"  Rol actual       : {claims_preview.get('role', 'sin rol')}")
        print(f"  Pediste admin    : {'sí' if make_admin else 'no'}")
        print(f"  Contraseña       : "
              f"{password or '(se generaría una temporal)'}")
        print("─" * 60)
        return 0

    # Se calcula ANTES de llamar, para que el password que se imprime sea
    # exactamente el que se envió. Si la cuenta ya existía, no sabemos la
    # contraseña actual y así lo decimos en vez de inventarla.
    generated = password is None
    password_to_use = password or generate_password()

    if existing is None:
        user = auth.create_user(
            email=email,
            password=password_to_use,
            display_name=display_name,
        )
        created = True
    else:
        # No se reescriben password ni nombre: si alguien ya está usando la
        # cuenta, tocarlos la dejaría fuera sin aviso.
        user = existing
        created = False
        password_to_use = None

    claims = dict(user.custom_claims or {})
    already_admin = claims.get("role") == "admin"

    if make_admin and not already_admin:
        claims["role"] = "admin"
        auth.set_custom_user_claims(user.uid, claims)

    print("─" * 60)
    print(f"  {'Cuenta creada' if created else 'Cuenta ya existente'}")
    print(f"  Correo    : {email}")
    print(f"  UID       : {user.uid}")
    # user.display_name, no el del argumento: si la cuenta ya existía, lo que
    # vale es lo que trae Auth, y ahí puede no haber nombre.
    print(f"  Nombre    : {user.display_name or '(sin definir, editable en la app)'}")

    if password_to_use:
        print(f"  Contraseña: {password_to_use}"
              + ("  (generada; envíala por WhatsApp y que la cambie)"
                 if generated else ""))
    else:
        print("  Contraseña: no se conoce (la cuenta ya existía).")
        print("             Si la olvidó, usa «Reset password» en la consola.")

    print(f"  Rol       : {claims.get('role', 'sin rol')}")
    print("─" * 60)

    if make_admin and already_admin:
        print("ℹ  Ya era admin; no se tocó el claim.")

    if user.disabled:
        print(
            "⚠  La cuenta está DESHABILITADA. Nadie podrá entrar con ella "
            "hasta que se reactive en la consola de Firebase Authentication."
        )

    print(
        "\nCierra sesión y vuelve a entrar en la app para que el token se "
        "refresque y el rol surta efecto."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crea una cuenta en Firebase Auth y le asigna un rol.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python create_user.py tu@correo.com --admin\n"
            "  python create_user.py paciente@correo.com --name \"Ana López\"\n"
            "  python create_user.py paciente@correo.com --dry-run\n"
        ),
    )
    parser.add_argument("email", help="Correo de la cuenta a crear o reutilizar")
    parser.add_argument("--name", help="Nombre que se muestra en la app")
    parser.add_argument(
        "--password",
        help="Contraseña a usar. Si se omite, se genera una temporal.",
    )
    parser.add_argument(
        "--admin",
        action="store_true",
        help="Otorga el claim role=admin (el mismo que exigen la UI y el backend)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra lo que haría sin escribir nada",
    )
    args = parser.parse_args()

    return create_user(
        email=args.email,
        password=args.password,
        display_name=args.name,
        make_admin=args.admin,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
