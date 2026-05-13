"""
Configuración central del backend Mercadona Autopilot.
Lee variables de entorno desde .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env desde la raíz del proyecto
_project_root = Path(__file__).resolve().parent.parent.parent
# ── API Keys ──────────────────────────────────────────────
# Pega tu clave de Gemini entre las comillas:
GEMINI_API_KEY = "AIzaSyCsX76xPfpgSCgZwDE1j-BJ3qpMNToT_rU"


# ── Modos ─────────────────────────────────────────────────
# Modo demo si no hay API key válida configurada
DEMO_MODE: bool = not bool(GEMINI_API_KEY) or not GEMINI_API_KEY.startswith("AIza")

# ── Base de datos ─────────────────────────────────────────
DB_PATH: str = os.getenv(
    "DB_PATH",
    str(_project_root / "src" / "backend" / "mercadona.db"),
)

# ── Modelo Gemini ─────────────────────────────────────────
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
