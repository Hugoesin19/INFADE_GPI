"""
Motor de Recomendaciones Proactivas — Mercadín 🦔
Genera contexto inteligente para el saludo personalizado de Mercadín
evaluando múltiples señales: hora, estación, productos próximos a caducar,
historial de compras, perfil del usuario y presupuesto.
"""

from __future__ import annotations

import random
from datetime import datetime, date


# ══════════════════════════════════════════════════════════════
#  ESTACIONALIDAD — Recetas y productos por mes
# ══════════════════════════════════════════════════════════════

SEASONAL_MAP = {
    1:  {"season": "invierno", "recipes": ["cocido madrileño", "lentejas estofadas", "sopa de pollo"],
         "products": ["naranjas", "mandarinas", "caldos"], "festivity": "Año Nuevo"},
    2:  {"season": "invierno", "recipes": ["fabada asturiana", "crema de calabaza", "tortilla española"],
         "products": ["legumbres", "verduras de raíz", "chocolate"], "festivity": None},
    3:  {"season": "primavera", "recipes": ["ensalada césar", "pasta pesto", "tortilla de patatas"],
         "products": ["espárragos", "fresas", "guisantes"], "festivity": "Semana Santa (posible)"},
    4:  {"season": "primavera", "recipes": ["arroz con verduras", "ensalada mixta", "pollo al horno"],
         "products": ["alcachofas", "habas", "fresas"], "festivity": "Semana Santa (posible)"},
    5:  {"season": "primavera", "recipes": ["paella valenciana", "gazpacho", "ensalada griega"],
         "products": ["cerezas", "tomates", "pepinos"], "festivity": None},
    6:  {"season": "verano", "recipes": ["gazpacho", "ensalada de pasta", "brochetas de pollo"],
         "products": ["sandía", "melón", "tomates", "fresas"], "festivity": "San Juan"},
    7:  {"season": "verano", "recipes": ["gazpacho", "ensalada caprese", "paella de marisco"],
         "products": ["sandía", "melón", "helados", "bebidas frías"], "festivity": None},
    8:  {"season": "verano", "recipes": ["ensalada tropical", "hamburguesas caseras", "arroz a banda"],
         "products": ["melocotones", "nectarinas", "helados"], "festivity": None},
    9:  {"season": "otoño", "recipes": ["setas a la plancha", "risotto", "lentejas con chorizo"],
         "products": ["setas", "uvas", "calabaza", "boniato"], "festivity": None},
    10: {"season": "otoño", "recipes": ["crema de calabaza", "cocido", "pasta boloñesa"],
         "products": ["calabaza", "castañas", "setas", "granada"], "festivity": "Halloween"},
    11: {"season": "otoño", "recipes": ["cocido madrileño", "sopa de cebolla", "asado de cerdo"],
         "products": ["caquis", "naranjas", "legumbres"], "festivity": None},
    12: {"season": "invierno", "recipes": ["asado navideño", "sopa de marisco", "canelones"],
         "products": ["turrón", "polvorones", "marisco", "cordero"], "festivity": "Navidad"},
}

# ── Momentos del día ─────────────────────────────────────────

TIME_SLOTS = {
    "madrugada":  (0, 6,   ["¿Trasnochando? Un buen café te espera"]),
    "mañana":     (6, 12,  ["Buenos días", "¡Buen día para hacer la compra!"]),
    "mediodía":   (12, 14, ["¡Hora de comer!", "¿Ya has pensado en la comida de hoy?"]),
    "tarde":      (14, 20, ["Buenas tardes", "¿Preparamos la cena de esta noche?"]),
    "noche":      (20, 24, ["Buenas noches", "¿Última compra del día?"]),
}

DAY_CONTEXT = {
    0: "lunes (vuelta a la rutina)",
    1: "martes",
    2: "miércoles (mitad de semana)",
    3: "jueves",
    4: "viernes (¡fin de semana a la vista!)",
    5: "sábado (¡buen día para cocinar algo especial!)",
    6: "domingo (día de descanso y buen comer)",
}


# ══════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL
# ══════════════════════════════════════════════════════════════

def generate_greeting_context(
    profile: dict,
    expiring_products: list[dict] | None = None,
    purchase_history: list[dict] | None = None,
) -> dict:
    """
    Genera el contexto completo para que el LLM (o el fallback)
    construya un saludo proactivo e inteligente.

    Args:
        profile: Perfil del usuario desde user_profiles
        expiring_products: Productos con days_to_expiry bajo
        purchase_history: Últimas compras del usuario

    Returns:
        dict con todo el contexto necesario para el saludo
    """
    now = datetime.now()
    month = now.month
    hour = now.hour
    weekday = now.weekday()

    # ── Contexto temporal ────────────────────────────────
    time_slot = "tarde"
    time_greeting = "Buenas tardes"
    for slot_name, (start, end, greetings) in TIME_SLOTS.items():
        if start <= hour < end:
            time_slot = slot_name
            time_greeting = random.choice(greetings)
            break

    seasonal = SEASONAL_MAP.get(month, SEASONAL_MAP[1])
    day_text = DAY_CONTEXT.get(weekday, "")

    # ── Contexto del usuario ─────────────────────────────
    user_name = profile.get("name", "").strip()
    budget_remaining = round(
        profile.get("monthly_budget", 200) - profile.get("month_spent", 0), 2
    )
    per_cart = profile.get("per_cart_budget", 25)
    allergens = profile.get("allergens", [])
    diet = profile.get("diet", "equilibrado")
    people = profile.get("people", 2)

    # ── Sugerencias de recetas (filtradas por alergias) ───
    suggested_recipes = list(seasonal["recipes"])
    # No sugerir recetas de marisco si alergia a crustáceos
    if "crustáceos" in allergens:
        suggested_recipes = [r for r in suggested_recipes if "marisco" not in r.lower()]

    # ── Productos de temporada ───────────────────────────
    seasonal_products = seasonal["products"]

    # ── Productos próximos a caducar ─────────────────────
    expiring_highlights = []
    if expiring_products:
        for p in expiring_products[:3]:
            expiring_highlights.append({
                "name": p["name"],
                "price": p["price"],
                "days_left": p["days_to_expiry"],
            })

    # ── Historial de compras ─────────────────────────────
    history_insights = []
    if purchase_history:
        for ph in purchase_history[:3]:
            history_insights.append({
                "date": ph.get("created_at", ""),
                "total": ph.get("total", 0),
                "notes": ph.get("notes", ""),
            })

    # ── Quick replies sugeridos ──────────────────────────
    quick_replies = _generate_quick_replies(
        time_slot, seasonal, expiring_highlights, diet
    )

    return {
        "time_context": {
            "slot": time_slot,
            "greeting": time_greeting,
            "hour": hour,
            "day": day_text,
            "weekday": weekday,
        },
        "season_context": {
            "season": seasonal["season"],
            "month": month,
            "festivity": seasonal.get("festivity"),
            "recipes": suggested_recipes,
            "products": seasonal_products,
        },
        "user_context": {
            "name": user_name,
            "people": people,
            "diet": diet,
            "allergens": allergens,
            "per_cart_budget": per_cart,
            "monthly_remaining": budget_remaining,
        },
        "expiring_products": expiring_highlights,
        "purchase_history": history_insights,
        "quick_replies": quick_replies,
    }


def _generate_quick_replies(
    time_slot: str,
    seasonal: dict,
    expiring: list[dict],
    diet: str,
) -> list[str]:
    """Genera 3 sugerencias rápidas como botones en el chat."""
    replies = []

    # Sugerencia basada en hora
    if time_slot in ("mañana", "madrugada"):
        replies.append("🥣 Compra para desayunos")
    elif time_slot == "mediodía":
        replies.append("🍝 Ingredientes para la comida")
    elif time_slot == "tarde":
        replies.append("🍽️ Preparar la cena de hoy")
    else:
        replies.append("🛒 Compra de la semana")

    # Sugerencia estacional
    if seasonal["recipes"]:
        recipe = random.choice(seasonal["recipes"])
        replies.append(f"👨‍🍳 Hacer {recipe}")

    # Sugerencia basada en caducidad
    if expiring:
        replies.append(f"🔥 Aprovechar ofertas frescas")
    elif diet == "alta proteína":
        replies.append("💪 Compra alta en proteína")
    else:
        replies.append("📋 Lista básica de la semana")

    return replies[:3]


# ══════════════════════════════════════════════════════════════
#  SALUDO DEMO (sin LLM)
# ══════════════════════════════════════════════════════════════

def build_demo_greeting(context: dict) -> str:
    """
    Genera un saludo determinista de Mercadín cuando no hay API key.
    Usa el contexto del motor de recomendaciones.
    """
    tc = context["time_context"]
    sc = context["season_context"]
    uc = context["user_context"]
    exp = context["expiring_products"]

    # Saludo base
    name_part = f", {uc['name']}" if uc["name"] else ""
    greeting = f"¡{tc['greeting']}{name_part}! 🦔"

    # Cuerpo del mensaje
    parts = [greeting]

    # Contexto temporal
    parts.append(f"Hoy es {tc['day']}.")

    # Estación y receta sugerida
    if sc["festivity"]:
        parts.append(f"Se acerca {sc['festivity']}, ¿preparamos algo especial?")
    elif sc["recipes"]:
        recipe = random.choice(sc["recipes"])
        parts.append(
            f"Estamos en {sc['season']}, perfecto para un buen "
            f"**{recipe}**. ¿Te apetece?"
        )

    # Productos próximos a caducar
    if exp:
        p = exp[0]
        parts.append(
            f"\n\n📢 ¡Oferta fresca! **{p['name']}** a solo "
            f"**{p['price']:.2f}€** (caduca en {p['days_left']} días)."
        )

    # Presupuesto
    if uc["monthly_remaining"] < 30:
        parts.append(
            f"\n⚠️ Te quedan **{uc['monthly_remaining']:.0f}€** este mes. "
            f"Haré una compra ajustada."
        )

    parts.append("\n\n¿En qué te puedo ayudar hoy?")

    return " ".join(parts)
