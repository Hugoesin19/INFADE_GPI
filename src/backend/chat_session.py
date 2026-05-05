"""
Gestión de Sesiones Conversacionales — Mercadín 🦔
Persistencia en SQLite para sesiones de chat, historial de compras
y memoria del usuario entre conversaciones.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlite3
from .config import DB_PATH


# ══════════════════════════════════════════════════════════════
#  ESQUEMAS DE TABLAS
# ══════════════════════════════════════════════════════════════

CHAT_SESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          TEXT PRIMARY KEY,
    user_id     INTEGER DEFAULT 1,
    messages    TEXT NOT NULL DEFAULT '[]',
    cart_state  TEXT NOT NULL DEFAULT '[]',
    constraints TEXT NOT NULL DEFAULT '{}',
    status      TEXT DEFAULT 'active',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

PURCHASE_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS purchase_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER DEFAULT 1,
    session_id  TEXT NOT NULL,
    products    TEXT NOT NULL,
    total       REAL NOT NULL,
    notes       TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);
"""


# ── Helpers ───────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_chat_tables() -> None:
    """Crea las tablas de sesiones y historial si no existen."""
    conn = _get_conn()
    conn.executescript(CHAT_SESSION_SCHEMA)
    conn.executescript(PURCHASE_HISTORY_SCHEMA)
    conn.close()


# ══════════════════════════════════════════════════════════════
#  SESIONES DE CHAT
# ══════════════════════════════════════════════════════════════

def create_session(user_id: int = 1) -> dict:
    """
    Crea una nueva sesión de chat y la persiste en SQLite.
    Returns: dict con los datos de la sesión.
    """
    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    conn = _get_conn()
    conn.execute(
        """INSERT INTO chat_sessions (id, user_id, messages, cart_state, constraints, status, created_at, updated_at)
           VALUES (?, ?, '[]', '[]', '{}', 'active', ?, ?)""",
        (session_id, user_id, now, now),
    )
    conn.commit()
    conn.close()

    return {
        "id": session_id,
        "user_id": user_id,
        "messages": [],
        "cart_state": [],
        "constraints": {},
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


def get_session(session_id: str) -> dict | None:
    """Recupera una sesión por su ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return None

    return _row_to_session(row)


def add_message(session_id: str, role: str, content: str) -> None:
    """
    Añade un mensaje al historial de la sesión.
    role: 'user' | 'assistant'
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT messages FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()

    if row is None:
        conn.close()
        return

    messages = json.loads(row["messages"])
    messages.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    })

    conn.execute(
        "UPDATE chat_sessions SET messages = ?, updated_at = ? WHERE id = ?",
        (json.dumps(messages, ensure_ascii=False), datetime.now().isoformat(), session_id),
    )
    conn.commit()
    conn.close()


def update_cart_state(session_id: str, cart_products: list[dict]) -> None:
    """Actualiza el estado del carrito en la sesión."""
    conn = _get_conn()
    # Serializar solo los campos necesarios del carrito
    cart_serializable = []
    for p in cart_products:
        cart_serializable.append({
            "id": p["id"],
            "name": p["name"],
            "brand": p["brand"],
            "category": p["category"],
            "subcategory": p.get("subcategory", ""),
            "price": p["price"],
            "unit_size": p.get("unit_size", 0),
            "size_format": p.get("size_format", ""),
            "packaging": p.get("packaging", ""),
            "allergens": p.get("allergens", []),
            "kcal_100g": p.get("kcal_100g", 0),
            "protein_100g": p.get("protein_100g", 0),
            "carbs_100g": p.get("carbs_100g", 0),
            "fat_100g": p.get("fat_100g", 0),
            "image_url": p.get("image_url", ""),
            "days_to_expiry": p.get("days_to_expiry", 180),
        })

    conn.execute(
        "UPDATE chat_sessions SET cart_state = ?, updated_at = ? WHERE id = ?",
        (json.dumps(cart_serializable, ensure_ascii=False), datetime.now().isoformat(), session_id),
    )
    conn.commit()
    conn.close()


def update_constraints(session_id: str, constraints: dict) -> None:
    """Actualiza las constraints acumuladas de la sesión."""
    conn = _get_conn()
    conn.execute(
        "UPDATE chat_sessions SET constraints = ?, updated_at = ? WHERE id = ?",
        (json.dumps(constraints, ensure_ascii=False), datetime.now().isoformat(), session_id),
    )
    conn.commit()
    conn.close()


def confirm_session(session_id: str) -> dict | None:
    """
    Marca una sesión como confirmada.
    Guarda la compra en purchase_history y devuelve la sesión final.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()

    if row is None:
        conn.close()
        return None

    session = _row_to_session(row)
    now = datetime.now().isoformat()

    # Marcar sesión como confirmada
    conn.execute(
        "UPDATE chat_sessions SET status = 'confirmed', updated_at = ? WHERE id = ?",
        (now, session_id),
    )

    # Calcular total
    cart = session["cart_state"]
    total = round(sum(p.get("price", 0) for p in cart), 2)

    # Extraer notas del historial (último mensaje del asistente o constraints)
    constraints = session.get("constraints", {})
    notes = constraints.get("notes", "compra general")

    # Guardar en purchase_history
    products_summary = json.dumps(
        [{"id": p["id"], "name": p["name"], "price": p["price"]} for p in cart],
        ensure_ascii=False,
    )

    conn.execute(
        """INSERT INTO purchase_history (user_id, session_id, products, total, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session["user_id"], session_id, products_summary, total, notes, now),
    )

    conn.commit()
    conn.close()

    session["status"] = "confirmed"
    return session


# ══════════════════════════════════════════════════════════════
#  HISTORIAL DE COMPRAS
# ══════════════════════════════════════════════════════════════

def get_purchase_history(user_id: int = 1, limit: int = 5) -> list[dict]:
    """Devuelve las últimas N compras del usuario."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM purchase_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()

    history = []
    for row in rows:
        d = dict(row)
        try:
            d["products"] = json.loads(d.get("products", "[]"))
        except json.JSONDecodeError:
            d["products"] = []
        history.append(d)

    return history


# ══════════════════════════════════════════════════════════════
#  HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════

def _row_to_session(row: sqlite3.Row) -> dict:
    """Convierte una fila SQLite a dict, parseando campos JSON."""
    d = dict(row)
    for field in ("messages", "cart_state"):
        raw = d.get(field, "[]")
        if isinstance(raw, str):
            try:
                d[field] = json.loads(raw)
            except json.JSONDecodeError:
                d[field] = []
    constraints_raw = d.get("constraints", "{}")
    if isinstance(constraints_raw, str):
        try:
            d["constraints"] = json.loads(constraints_raw)
        except json.JSONDecodeError:
            d["constraints"] = {}
    return d
