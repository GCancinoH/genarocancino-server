"""
Otorga (o revoca) el rol admin a un usuario de Firebase Auth.

El rol vive en el custom claim `role`. Es la MISMA fuente de verdad que
usan:
  - adminGuard (UI):       claims.role === 'admin'
  - backend Flask:         decorators.require_role('admin')
  - firestore.rules:       request.auth.token.role == 'admin'

Uso:
    python set_admin_role.py tu@correo.com          # otorgar admin
    python set_admin_role.py tu@correo.com --off    # revocar admin

NOTA: los claims viven en el ID token. Después de correrlo, cierra sesión
y vuelve a entrar en la app (o espera ~1 h) para que el token se refresque.
"""

import os
import sys

import firebase_admin
from firebase_admin import auth, credentials

# --- Configuración ---------------------------------------------------------

PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "gc-nutrition")

# Ruta a la service account. Prioriza la variable de entorno y si no,
# usa la que está junto a este script.
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


def set_role(email: str, make_admin: bool) -> None:
    """Asigna o revoca el claim `role: 'admin'` conservando el resto."""
    _init_app()

    user = auth.get_user_by_email(email)
    claims = dict(user.custom_claims or {})
    if make_admin:
        claims["role"] = "admin"
    else:
        # Si era admin, quitamos el rol; si era player lo dejamos igual.
        if claims.get("role") == "admin":
            claims.pop("role", None)

    auth.set_custom_user_claims(user.uid, claims)

    action = "otorgado" if make_admin else "revocado"
    print(f"✔ Rol admin {action} para {email} (uid: {user.uid})")
    print(f"  Claims actuales: {claims}")
    print(
        "\nCierra sesión y vuelve a entrar en la app para que el token "
        "se refresque y el rol surta efecto."
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    target_email = sys.argv[1]
    is_admin = "--off" not in sys.argv
    set_role(target_email, is_admin)
