"""
Módulo 3 — Enjambre Multi-Agente.
Tres agentes (Nutricionista, Logístico, Financiero) negocian la cesta final.

Implementación dual:
  - Con API key: usa LangGraph + Gemini para razonamiento real
  - Sin API key: lógica determinista con scoring
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .config import DEMO_MODE, GEMINI_API_KEY, GEMINI_MODEL


@dataclass
class CartState:
    """Estado compartido entre los agentes."""
    available_products: list[dict] = field(default_factory=list)
    selected_products: list[dict] = field(default_factory=list)
    budget: float = 25.0
    people: int = 2
    diet: str = "equilibrado"
    meal_type: str = "general"
    notes: str = ""
    total: float = 0.0
    agent_logs: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
#  MODO DEMO — Lógica determinista sin LLM
# ═══════════════════════════════════════════════════════════

def _demo_nutritionist(state: CartState) -> CartState:
    """Agente Nutricionista (demo): selecciona productos variados por categoría."""
    categories_needed = set()
    
    if state.meal_type in ("comida", "cena", "general", "semanal"):
        categories_needed = {"carne", "verduras", "cereales", "aceites"}
    elif state.meal_type == "desayuno":
        categories_needed = {"lácteos", "cereales", "panadería"}
    
    if not categories_needed:
        categories_needed = {"carne", "verduras", "cereales", "aceites", "legumbres"}

    selected = []
    used_categories = set()

    # Garantizar al menos un producto por categoría necesaria
    for cat in categories_needed:
        for product in state.available_products:
            if product["category"] == cat and cat not in used_categories:
                selected.append(product)
                used_categories.add(cat)
                break

    # Completar con productos de alto valor nutricional
    for product in state.available_products:
        if product not in selected and len(selected) < state.people + 4:
            if product.get("protein_100g", 0) > 5:
                selected.append(product)

    state.selected_products = selected
    state.agent_logs.append(
        f"🥗 Nutricionista: Seleccionados {len(selected)} productos "
        f"de {len(used_categories)} categorías para dieta {state.diet}."
    )
    return state


def _demo_logistics(state: CartState) -> CartState:
    """Agente Logístico (demo): prioriza marca Hacendado."""
    # Reordenar: Hacendado primero
    hacendado = [p for p in state.selected_products if p["brand"] == "Hacendado"]
    other = [p for p in state.selected_products if p["brand"] != "Hacendado"]
    
    # Sustituir productos no-Hacendado si hay alternativa
    for i, product in enumerate(other):
        alternative = next(
            (p for p in state.available_products
             if p["brand"] == "Hacendado"
             and p["category"] == product["category"]
             and p not in hacendado),
            None,
        )
        if alternative:
            hacendado.append(alternative)
        else:
            hacendado.append(product)

    state.selected_products = hacendado
    pct = sum(1 for p in state.selected_products if p["brand"] == "Hacendado") / max(len(state.selected_products), 1) * 100
    state.agent_logs.append(
        f"📦 Logístico: {pct:.0f}% de la cesta es marca Hacendado (máximo margen)."
    )
    return state


def _demo_financial(state: CartState) -> CartState:
    """Agente Financiero (demo): ajusta la cesta al presupuesto."""
    # Ordenar por precio ascendente
    state.selected_products.sort(key=lambda p: p["price"])

    final_cart = []
    running_total = 0.0

    for product in state.selected_products:
        if running_total + product["price"] <= state.budget:
            final_cart.append(product)
            running_total += product["price"]

    # Si queda presupuesto, añadir más productos disponibles
    if running_total < state.budget * 0.7:
        for product in state.available_products:
            if product not in final_cart and running_total + product["price"] <= state.budget:
                final_cart.append(product)
                running_total += product["price"]

    state.selected_products = final_cart
    state.total = round(running_total, 2)
    state.agent_logs.append(
        f"💰 Financiero: Cesta final {state.total}€ / {state.budget}€ presupuesto. "
        f"Ahorro: {state.budget - state.total:.2f}€."
    )
    return state


def run_agents_demo(
    available_products: list[dict],
    constraints: dict,
) -> CartState:
    """Ejecuta los 3 agentes en modo demo (determinista)."""
    state = CartState(
        available_products=available_products,
        budget=constraints.get("budget", 25.0),
        people=constraints.get("people", 2),
        diet=constraints.get("diet", "equilibrado"),
        meal_type=constraints.get("meal_type", "general"),
        notes=constraints.get("notes", ""),
    )

    # Ronda 1 de negociación
    state = _demo_nutritionist(state)
    state = _demo_logistics(state)
    state = _demo_financial(state)

    return state


# ═══════════════════════════════════════════════════════════
#  MODO LLM — LangGraph + Gemini
# ═══════════════════════════════════════════════════════════

def _build_product_summary(products: list[dict], max_items: int = 15) -> str:
    """Resume productos como texto para el prompt LLM."""
    lines = []
    for p in products[:max_items]:
        lines.append(f"- {p['name']} ({p['brand']}) | {p['price']}€ | {p['category']} | P:{p.get('protein_100g',0)}g C:{p.get('carbs_100g',0)}g G:{p.get('fat_100g',0)}g")
    return "\n".join(lines)


def _llm_agent_call(role: str, instruction: str, state_context: str) -> str:
    """Llamada genérica a Gemini para un agente."""
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""Eres el agente {role} del sistema Mercadona Autopilot.

{instruction}

Estado actual:
{state_context}

Responde ÚNICAMENTE con un JSON con estas claves:
- "selected_ids": lista de IDs de productos a incluir en la cesta
- "reasoning": string con tu razonamiento en 1-2 frases
"""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text.strip()


def run_agents_llm(
    available_products: list[dict],
    constraints: dict,
) -> CartState:
    """Ejecuta los 3 agentes con LLM (Gemini)."""
    state = CartState(
        available_products=available_products,
        budget=constraints.get("budget", 25.0),
        people=constraints.get("people", 2),
        diet=constraints.get("diet", "equilibrado"),
        meal_type=constraints.get("meal_type", "general"),
        notes=constraints.get("notes", ""),
    )

    product_summary = _build_product_summary(available_products, max_items=30)
    context_base = (
        f"Presupuesto: {state.budget}€\n"
        f"Personas: {state.people}\n"
        f"Dieta: {state.diet}\n"
        f"Tipo comida: {state.meal_type}\n"
        f"Notas: {state.notes}\n\n"
        f"Productos disponibles:\n{product_summary}"
    )

    # Mapa de id -> producto para búsqueda rápida
    id_map = {p["id"]: p for p in available_products}

    # ── Agente Nutricionista ──────────────────────────────
    try:
        raw = _llm_agent_call(
            "NUTRICIONISTA",
            "Selecciona productos que formen una cesta nutricionalmente equilibrada. "
            "Incluye variedad de categorías. Prioriza alto valor nutricional.",
            context_base,
        )
        data = _parse_agent_json(raw)
        ids = data.get("selected_ids", [])
        state.selected_products = [id_map[i] for i in ids if i in id_map]
        state.agent_logs.append(f"🥗 Nutricionista: {data.get('reasoning', '')}")
    except Exception as e:
        # Fallback al demo
        state = _demo_nutritionist(state)

    # ── Agente Logístico ──────────────────────────────────
    current_ids = [p["id"] for p in state.selected_products]
    logistics_context = context_base + f"\n\nCesta actual (IDs): {current_ids}"
    try:
        raw = _llm_agent_call(
            "LOGÍSTICO",
            "Revisa la cesta y prioriza productos de marca Hacendado (mayor margen). "
            "Sustituye productos de otras marcas por Hacendado cuando sea posible.",
            logistics_context,
        )
        data = _parse_agent_json(raw)
        ids = data.get("selected_ids", [])
        state.selected_products = [id_map[i] for i in ids if i in id_map]
        state.agent_logs.append(f"📦 Logístico: {data.get('reasoning', '')}")
    except Exception:
        state = _demo_logistics(state)

    # ── Agente Financiero ─────────────────────────────────
    current_ids = [p["id"] for p in state.selected_products]
    financial_context = context_base + f"\n\nCesta actual (IDs): {current_ids}\nTotal actual: {sum(p['price'] for p in state.selected_products):.2f}€"
    try:
        raw = _llm_agent_call(
            "FINANCIERO",
            f"Ajusta la cesta para que el total no supere {state.budget}€. "
            "Elimina los productos menos esenciales si es necesario. "
            "Si queda margen, añade productos de valor.",
            financial_context,
        )
        data = _parse_agent_json(raw)
        ids = data.get("selected_ids", [])
        state.selected_products = [id_map[i] for i in ids if i in id_map]
        state.total = round(sum(p["price"] for p in state.selected_products), 2)
        state.agent_logs.append(f"💰 Financiero: {data.get('reasoning', '')}")
    except Exception:
        state = _demo_financial(state)

    if state.total == 0:
        state.total = round(sum(p["price"] for p in state.selected_products), 2)

    return state


def _parse_agent_json(raw: str) -> dict:
    """Parsea JSON de respuesta del agente, limpiando markdown."""
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])
    return json.loads(raw)


# ═══════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════

def run_agents(
    available_products: list[dict],
    constraints: dict,
) -> CartState:
    """
    Ejecuta el enjambre multi-agente.
    Usa LLM si hay API key, sino modo demo.
    """
    if DEMO_MODE:
        return run_agents_demo(available_products, constraints)
    else:
        return run_agents_llm(available_products, constraints)
