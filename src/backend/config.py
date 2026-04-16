"""
Configuración central del backend Mercadona Autopilot.
Lee variables de entorno desde .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env desde la raíz del proyecto
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")

# ── API Keys ──────────────────────────────────────────────
GEMINI_API_KEY = "AQ.Ab8RN6KRnEVPE7h1UUlL_h3q5-OQWPyQ1KjhRxidc_e24kWTrQ"
#"AIzaSyCsX76xPfpgSCgZwDE1j-BJ3qpMNToT_rU"

# ── Modos ─────────────────────────────────────────────────
# Si no hay API key, el sistema funciona con respuestas demo
DEMO_MODE: bool = not bool(GEMINI_API_KEY)

# ── Base de datos ─────────────────────────────────────────
DB_PATH: str = os.getenv(
    "DB_PATH",
    str(_project_root / "src" / "backend" / "mercadona.db"),
)

# ── Modelo Gemini ─────────────────────────────────────────
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
