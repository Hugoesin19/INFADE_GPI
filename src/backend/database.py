"""
Base de datos SQLite de productos Mercadona.
Soporta tanto seed data manual como datos scrapeados de la API.
"""

import json
import sqlite3
from typing import Optional

from .config import DB_PATH

# ── Esquema ───────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mercadona_id    TEXT    UNIQUE,
    name            TEXT    NOT NULL,
    brand           TEXT    NOT NULL DEFAULT 'Hacendado',
    category        TEXT    NOT NULL,
    subcategory     TEXT    NOT NULL DEFAULT '',
    price           REAL    NOT NULL,
    unit_size       REAL    DEFAULT 0,
    size_format     TEXT    DEFAULT '',
    packaging       TEXT    DEFAULT '',
    allergens       TEXT    NOT NULL DEFAULT '[]',
    kcal_100g       REAL    DEFAULT 0,
    protein_100g    REAL    DEFAULT 0,
    carbs_100g      REAL    DEFAULT 0,
    fat_100g        REAL    DEFAULT 0,
    image_url       TEXT    DEFAULT '',
    share_url       TEXT    DEFAULT '',
    days_to_expiry  INTEGER DEFAULT 180
);
"""


# ── Funciones ─────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Crea las tablas si no existen (no sobreescribe datos existentes)."""
    conn = _get_conn()
    conn.executescript(_SCHEMA)
    conn.close()
    # Inicializar tabla de perfil de usuario
    from .user_profile import init_profile_table
    init_profile_table()


def get_all_products(queries: list[str] = None) -> list[dict]:
    """Devuelve productos filtrados por palabras clave o todos si no hay."""
    conn = _get_conn()
    if not queries:
        rows = conn.execute("SELECT * FROM products").fetchall()
    else:
        # Buscar por cada keyword y mezclar resultados (máx 30 por keyword)
        seen_ids = set()
        rows = []
        for q in queries:
            word = f"%{q}%"
            partial = conn.execute(
                "SELECT * FROM products WHERE name LIKE ? OR category LIKE ? OR subcategory LIKE ? LIMIT 30",
                (word, word, word)
            ).fetchall()
            for r in partial:
                rid = r["id"]
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    rows.append(r)

        if not rows:
            rows = conn.execute("SELECT * FROM products").fetchall()

    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_safe_products(excluded_allergens: list[str], search_queries: list[str] = None) -> list[dict]:
    """
    Devuelve productos que coinciden con las queries y NO contienen alérgenos indicados.
    """
    all_products = get_all_products(search_queries)
    if not excluded_allergens:
        return all_products

    safe = []
    for p in all_products:
        product_allergens = set(p.get("allergens", []))
        if not product_allergens.intersection(excluded_allergens):
            safe.append(p)
    return safe


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    # Parsear allergens JSON si existe
    allergens_raw = d.get("allergens", "[]")
    if isinstance(allergens_raw, str):
        try:
            d["allergens"] = json.loads(allergens_raw)
        except json.JSONDecodeError:
            d["allergens"] = []
    # Defaults para campos opcionales
    for field in ("kcal_100g", "protein_100g", "carbs_100g", "fat_100g", "unit_size"):
        if d.get(field) is None:
            d[field] = 0.0
    if d.get("days_to_expiry") is None:
        d["days_to_expiry"] = 180
    for field in ("image_url", "packaging", "size_format", "subcategory", "brand"):
        if d.get(field) is None:
            d[field] = ""
    return d
