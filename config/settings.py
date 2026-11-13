"""Configuracion de Django para Cambell."""
import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(valor, defecto=False):
    if valor is None:
        return defecto
    return str(valor).strip().lower() in ("1", "true", "yes", "si", "on")


# --- Seguridad ---------------------------------------------------------------
DEBUG = _bool(os.getenv("DEBUG"), True)
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        # Solo para desarrollo local. En produccion SECRET_KEY es obligatoria.
        SECRET_KEY = "dev-solo-desarrollo-no-usar-en-produccion"
    else:
        raise RuntimeError("Define SECRET_KEY en el archivo .env")

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]

# --- Aplicaciones ------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Cambell
    "usuarios",
    "solicitudes",
    "pagos",
    "mensajeria",
    "anuncios",
    "seguridad",
    "tareas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Si la contrasena no cumple la politica, obliga a cambiarla antes de seguir.
    "usuarios.middleware.ForzarCambioPasswordMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "usuarios.contexto.navegacion",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Base de datos -----------------------------------------------------------
if os.getenv("DB_ENGINE", "sqlite").lower() == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "cambell"),
            "USER": os.getenv("DB_USER", "root"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Autenticacion -----------------------------------------------------------
AUTH_USER_MODEL = "usuarios.Usuario"
LOGIN_URL = "usuarios:login"
LOGIN_REDIRECT_URL = "usuarios:panel"
LOGOUT_REDIRECT_URL = "usuarios:login"

# La contrasena se valida con reglas propias en el formulario de registro
# (8-64 caracteres, mayuscula, minuscula y numero), igual que en la version Java.
AUTH_PASSWORD_VALIDATORS = []

# --- Internacionalizacion ----------------------------------------------------
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# --- Archivos estaticos y subidos -------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Documentos y selfies de los trabajadores. A diferencia de la version Java
# (donde /uploads/** era publico), aqui NO se sirven por URL publica.
MEDIA_ROOT = BASE_DIR / "uploads"
MEDIA_URL = "/uploads/"
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# --- Correo ------------------------------------------------------------------
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.gmail.com"
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = "no-reply@cambell.local"

# --- Reglas de negocio (se usan en fases siguientes) -------------------------
COMISION_PLATAFORMA = 0.03  # 3 % por servicio
UMBRAL_VERIFICACION_FACIAL = 75
# Suscripción premium (pago simulado). Con probabilidad 1.0 siempre se aprueba.
COSTO_SUSCRIPCION_MENSUAL = Decimal(os.getenv("COSTO_SUSCRIPCION_MENSUAL", "19900"))
PROBABILIDAD_PAGO_APROBADO = float(os.getenv("PROBABILIDAD_PAGO_APROBADO", "1.0"))

# --- Verificación facial (patrón Strategy) -----------------------------------
# Con credenciales se usa Face++; sin ellas se usa la estrategia manual y el
# intento queda para revisión de un administrador. Así el proyecto funciona
# aunque no se configure ningún servicio externo.
FACEPP_API_KEY = os.getenv("FACEPP_API_KEY", "")
FACEPP_API_SECRET = os.getenv("FACEPP_API_SECRET", "")
FACEPP_API_URL = os.getenv(
    "FACEPP_API_URL", "https://api-us.faceplusplus.com/facepp/v3/compare"
)

# --- Tareas programadas (equivale a TareasProgramadasService.java) -----------
# Se ejecutan con: python manage.py tareas_programadas
HORAS_REASIGNACION = int(os.getenv("HORAS_REASIGNACION", "1"))
HORAS_SOLICITUD_NO_ATENDIDA = int(os.getenv("HORAS_SOLICITUD_NO_ATENDIDA", "24"))
UMBRAL_REPORTES_SUSPENSION = int(os.getenv("UMBRAL_REPORTES_SUSPENSION", "3"))
DIAS_AVISO_DOCUMENTO = int(os.getenv("DIAS_AVISO_DOCUMENTO", "30"))
DIAS_RECORDATORIO_CALIFICACION = int(os.getenv("DIAS_RECORDATORIO_CALIFICACION", "2"))
DIAS_AVISO_SUSCRIPCION = int(os.getenv("DIAS_AVISO_SUSCRIPCION", "7"))
DIAS_RETENCION_ARCHIVOS = int(os.getenv("DIAS_RETENCION_ARCHIVOS", "365"))

# --- Seguridad de las cuentas ------------------------------------------------
# Intentos fallidos antes de bloquear temporalmente la cuenta y minutos del bloqueo.
MAX_INTENTOS_FALLIDOS = int(os.getenv("MAX_INTENTOS_FALLIDOS", "5"))
MINUTOS_BLOQUEO = int(os.getenv("MINUTOS_BLOQUEO", "15"))
# Horas de vigencia del enlace para restablecer la contrasena.
HORAS_TOKEN_RECUPERACION = int(os.getenv("HORAS_TOKEN_RECUPERACION", "1"))
