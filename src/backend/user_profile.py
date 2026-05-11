"""
Módulo de Perfil de Usuario — Mercadona Autopilot.
Gestiona preferencias, alergias y presupuesto mensual del hogar.
Perfil único local almacenado en SQLite (tabla user_profiles).
"""

from __future__ import annotations

import json
from datetime import datetime, date

from .config import DB_PATH

import sqlite3

# ── Esquema ───────────────────────────────────────────────

PROFILE_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    name            TEXT    DEFAULT '',
    people          INTEGER DEFAULT 2,
    allergens       TEXT    DEFAULT '[]',
    diet            TEXT    DEFAULT 'equilibrado',
    monthly_budget  REAL    DEFAULT 200.0,
    per_cart_budget  REAL   DEFAULT 25.0,
    month_spent     REAL    DEFAULT 0.0,
    month_start     TEXT    DEFAULT '',
    preferences     TEXT    DEFAULT '',
    brand_preference TEXT   DEFAULT 'Hacendado',
    created_at      TEXT    DEFAULT '',
    updated_at      TEXT    DEFAULT ''
);
"""


# ── Helpers ───────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convierte una fila SQLite a dict, parseando allergens JSON."""
    d = dict(row)
    allergens_raw = d.get("allergens", "[]")
    if isinstance(allergens_raw, str):
        try:
            d["allergens"] = json.loads(allergens_raw)
        except json.JSONDecodeError:
            d["allergens"] = []
    return d


def _current_month_start() -> str:
    """Devuelve el primer día del mes actual en ISO format."""
    today = date.today()
    return today.replace(day=1).isoformat()


def init_profile_table() -> None:
    """Crea la tabla user_profiles si no existe."""
    conn = _get_conn()
    conn.executescript(PROFILE_SCHEMA)
    conn.close()


# ── CRUD ──────────────────────────────────────────────────

def get_profile() -> dict:
    """
    Devuelve el perfil del usuario.
    Si no existe, crea uno con valores por defecto.
    Si cambió el mes, reinicia el gasto mensual automáticamente.
    """
    conn = _get_conn()

    row = conn.execute("SELECT * FROM user_profiles WHERE id = 1").fetchone()

    if row is None:
        # Crear perfil por defecto
        now = datetime.now().isoformat()
        month_start = _current_month_start()
        conn.execute(
            """INSERT INTO user_profiles (id, name, people, allergens, diet,
               monthly_budget, per_cart_budget, month_spent, month_start,
               preferences, brand_preference, created_at, updated_at)
               VALUES (1, '', 2, '[]', 'equilibrado', 200.0, 25.0, 0.0, ?, '', 'Hacendado', ?, ?)""",
            (month_start, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM user_profiles WHERE id = 1").fetchone()

    profile = _row_to_dict(row)

    # Auto-reset si cambió el mes
    current_month = _current_month_start()
    if profile.get("month_start", "") != current_month:
        conn.execute(
            "UPDATE user_profiles SET month_spent = 0.0, month_start = ?, updated_at = ? WHERE id = 1",
            (current_month, datetime.now().isoformat()),
        )
        conn.commit()
        profile["month_spent"] = 0.0
        profile["month_start"] = current_month

    conn.close()
    return profile


def update_profile(data: dict) -> dict:
    """
    Actualiza el perfil con los campos proporcionados.
    Solo actualiza campos válidos, ignora los desconocidos.
    """
    valid_fields = {
        "name", "people", "allergens", "diet",
        "monthly_budget", "per_cart_budget", "preferences", "brand_preference"
    }

    updates = {}
    for key, value in data.items():
        if key in valid_fields:
            if key == "allergens" and isinstance(value, list):
                updates[key] = json.dumps(value)
            else:
                updates[key] = value

    if not updates:
        return get_profile()

    updates["updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values())

    conn = _get_conn()
    conn.execute(
        f"UPDATE user_profiles SET {set_clause} WHERE id = 1",
        values,
    )
    conn.commit()
    conn.close()

    return get_profile()


def add_spending(amount: float) -> dict:
    """
    Registra un gasto y devuelve el perfil actualizado
    con el presupuesto restante del mes.
    """
    conn = _get_conn()
    now = datetime.now().isoformat()

    conn.execute(
        "UPDATE user_profiles SET month_spent = month_spent + ?, updated_at = ? WHERE id = 1",
        (round(amount, 2), now),
    )
    conn.commit()
    conn.close()

    return get_profile()
