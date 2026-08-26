"""
Configuración del backend Pulso Háptico.

Variables de entorno relevantes (podés definirlas antes de levantar el server
o crear un archivo .env y exportarlas):

    PULSO_SERIAL_PORT     Puerto serial del Arduino. Ej: COM5, /dev/ttyUSB0
    PULSO_BAUDRATE        Baudrate serial. Default 115200 (debe matchear el .ino)
    PULSO_MOCK_ARDUINO    "1" para correr sin Arduino real (simula telemetría).
                          Útil para desarrollar la app mobile sin hardware.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "dev-secret-key-cambiar-en-produccion"

DEBUG = True

# "*" para que la app mobile (celular en la misma red Wi-Fi) pueda pegarle
# a este server por IP local (ej: 192.168.0.x:8000).
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "corsheaders",
    "haptic",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

# MVP: la app mobile no requiere login, así que abrimos CORS totalmente.
CORS_ALLOW_ALL_ORIGINS = True

ROOT_URLCONF = "pulso_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "pulso_backend.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
}

# -----------------------------------------------------------------
# Configuración específica de Pulso Háptico
# -----------------------------------------------------------------
PULSO_SERIAL_PORT = os.environ.get("PULSO_SERIAL_PORT", "")
PULSO_BAUDRATE = int(os.environ.get("PULSO_BAUDRATE", "115200"))
PULSO_MOCK_ARDUINO = os.environ.get("PULSO_MOCK_ARDUINO", "0") == "1"

# Umbrales delta (smooth_bpm - baseline_bpm) -> política. Mismos valores que
# usaba la maqueta CLI original; se pueden ajustar acá sin tocar el Arduino.
PULSO_POLICY_THRESHOLDS = {
    "calm_down": 33,   # delta >= 33
    "breath": 19,      # 19 <= delta < 33
    "awareness": 9,    # 9 <= delta < 19
    # delta < 9 -> reassure
}

# Tiempo mínimo entre reenvíos de la misma política en modo automático.
PULSO_MIN_SECONDS_BETWEEN_SAME_POLICY = 8.0
