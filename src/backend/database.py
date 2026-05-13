"""
Base de datos SQLite de productos Mercadona.
Soporta tanto seed data manual como datos scrapeados de la API.
Incluye helpers para el motor de recomendaciones (productos próximos a caducar).
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
    # Inicializar tablas de chat y historial
    from .chat_session import init_chat_tables
    init_chat_tables()


def get_all_products(queries: list[str] = None) -> list[dict]:
    """Devuelve productos filtrados por palabras clave con ranking inteligente, o todos si no hay queries."""
    conn = _get_conn()
    if not queries:
        rows = conn.execute("SELECT * FROM products").fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]

    # Búsqueda inteligente con ranking de relevancia
    seen_ids = set()
    all_candidates = []

    for q in queries:
        word = f"%{q}%"
        partial = conn.execute(
            "SELECT * FROM products WHERE name LIKE ? OR category LIKE ? OR subcategory LIKE ? LIMIT 100",
            (word, word, word)
        ).fetchall()

        q_lower = q.lower().strip()
        q_words = set(q_lower.split())

        for row in partial:
            p = _row_to_dict(row)
            if p["id"] in seen_ids:
                continue
            seen_ids.add(p["id"])

            score = _score_product_relevance(p, q_lower, q_words)
            all_candidates.append((score, p["price"], p))

    conn.close()

    if not all_candidates:
        # Fallback: devolver todos los productos
        conn2 = _get_conn()
        rows = conn2.execute("SELECT * FROM products").fetchall()
        conn2.close()
        return [_row_to_dict(r) for r in rows]

    # Ordenar por score DESC, luego precio ASC
    all_candidates.sort(key=lambda x: (-x[0], x[1]))
    return [item[2] for item in all_candidates]


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


def search_products_smart(query: str, limit: int = 5) -> list[dict]:
    """
    Búsqueda inteligente de productos por relevancia.
    Devuelve los mejores candidatos para un ingrediente específico.
    Usado por el LLM translator para construir el catálogo del prompt.
    """
    conn = _get_conn()
    word = f"%{query}%"
    rows = conn.execute(
        "SELECT * FROM products WHERE name LIKE ? OR subcategory LIKE ? LIMIT 100",
        (word, word)
    ).fetchall()
    conn.close()

    q_lower = query.lower().strip()
    q_words = set(q_lower.split())
    scored = []

    for row in rows:
        p = _row_to_dict(row)
        score = _score_product_relevance(p, q_lower, q_words)
        scored.append((score, p["price"], p))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [item[2] for item in scored[:limit]]


def _score_product_relevance(product: dict, q_lower: str, q_words: set) -> int:
    """
    Calcula un score de relevancia entre un producto y un query de búsqueda.
    Prioriza matches exactos y por palabra completa sobre substrings.
    """
    name_l = product["name"].lower()
    sub_l = product.get("subcategory", "").lower()
    name_words = set(name_l.split())
    score = 0

    # Match exacto del nombre completo
    if name_l == q_lower:
        score = 100
    # Nombre empieza por el query
    elif name_l.startswith(q_lower + " ") or name_l.startswith(q_lower):
        score = 80
    # Query es una PALABRA COMPLETA en el nombre (no substring)
    elif q_lower in name_words:
        score = 60
    # Todas las palabras del query están como palabras completas en el nombre
    elif q_words and len(q_words) > 1 and q_words.issubset(name_words):
        score = 55
    # Match exacto en subcategoría
    elif sub_l == q_lower:
        score = 50
    # Subcategoría contiene el query como palabra completa
    elif q_lower in set(sub_l.split()):
        score = 45
    # Substring en nombre (último recurso — lo que causaba los problemas)
    elif q_lower in name_l:
        score = 20
    # Substring en subcategoría
    elif q_lower in sub_l:
        score = 15

    # Bonus: marca Hacendado
    if product["brand"] == "Hacendado":
        score += 3

    # Penalización: nombre mucho más largo que el query (menos probable que sea relevante)
    len_ratio = len(name_l) / max(len(q_lower), 1)
    if len_ratio > 5:
        score -= 5

    return score


def get_expiring_products(limit: int = 5) -> list[dict]:
    """
    Devuelve los productos con menor days_to_expiry.
    Usado por el motor de recomendaciones proactivas de Mercadín.
    """
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM products WHERE days_to_expiry > 0 ORDER BY days_to_expiry ASC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_products_by_ids(product_ids: list[int]) -> list[dict]:
    """Devuelve productos por sus IDs."""
    if not product_ids:
        return []
    conn = _get_conn()
    placeholders = ",".join("?" * len(product_ids))
    rows = conn.execute(
        f"SELECT * FROM products WHERE id IN ({placeholders})",
        product_ids
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


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
