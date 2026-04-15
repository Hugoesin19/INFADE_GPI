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
    search_queries: list[str] = field(default_factory=list)
    total: float = 0.0
    agent_logs: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
#  MODO DEMO — Lógica determinista sin LLM
# ═══════════════════════════════════════════════════════════

def _demo_nutritionist(state: CartState) -> CartState:
    """Agente Nutricionista: busca los ingredientes reales de la receta pedida."""
    selected = []
    used_ids = set()

    def _find_best(keyword: str) -> dict | None:
        """Encuentra el mejor producto para un ingrediente con scoring de relevancia."""
        candidates = []
        kw = keyword.lower()
        # Categorías de comida fresca (preferidas para recetas)
        fresh_cats = {"carne", "verdura y fruta", "huevos, leche y mantequilla",
                      "arroz, legumbres y pasta", "aceite, especias y salsas"}
        # Palabras que indican que un producto NO es el ingrediente real
        noise_words = {"sorpresa", "sabor", "aroma", "ambientador", "gel", "jabón"}

        for p in state.available_products:
            if p["id"] in used_ids:
                continue
            name_l = p["name"].lower()
            cat_l = p["category"].lower()
            sub_l = p.get("subcategory", "").lower()
            if kw in name_l or kw in cat_l or kw in sub_l:
                # Penalizar productos engañosos
                if any(nw in name_l for nw in noise_words):
                    continue  # Descartar completamente

                score = 0
                # El nombre empieza con el keyword → producto real
                if name_l.startswith(kw):
                    score += 100
                # La subcategoría contiene el keyword → categoría directa
                elif kw in sub_l:
                    score += 80
                # Keyword como palabra en el nombre
                else:
                    # "sazonador para X" → score bajo
                    words = name_l.split()
                    if kw in words or any(w.startswith(kw) for w in words):
                        score += 60
                    else:
                        score += 30

                # Bonus comida fresca
                if cat_l in fresh_cats:
                    score += 15
                # Bonus Hacendado
                if p["brand"] == "Hacendado":
                    score += 10
                candidates.append((score, p["price"], p))
        if not candidates:
            return None
        # Mayor score primero, luego precio más bajo
        candidates.sort(key=lambda x: (-x[0], x[1]))
        return candidates[0][2]

    # 1. Buscar un producto por cada ingrediente de la receta
    for q in state.search_queries:
        best = _find_best(q)
        if best:
            selected.append(best)
            used_ids.add(best["id"])

    # 2. Si no se encontró nada (no hay queries), seleccionar por categoría base
    if not selected:
        base_cats = {"Carne", "Arroz, legumbres y pasta", "Verdura y fruta",
                     "Aceite, especias y salsas", "Huevos, leche y mantequilla"}
        for p in state.available_products:
            if p["category"] in base_cats and p["id"] not in used_ids:
                selected.append(p)
                used_ids.add(p["id"])
                if len(selected) >= 5:
                    break

    state.selected_products = selected

    # Calcular macros totales
    tkcal = tprot = tcarb = tfat = 0.0
    for p in state.selected_products:
        factor = (p.get("unit_size", 0.0) or 0) * 10
        if factor == 0:
            factor = 1
        tkcal += p.get("kcal_100g", 0) * factor
        tprot += p.get("protein_100g", 0) * factor
        tcarb += p.get("carbs_100g", 0) * factor
        tfat += p.get("fat_100g", 0) * factor

    macro_text = f"[Kcal: {int(tkcal)} | Proteína: {int(tprot)}g | Carbs: {int(tcarb)}g | Grasas: {int(tfat)}g]"
    ingredients_found = ", ".join(q for q in state.search_queries) or "general"
    state.agent_logs.append(
        f"🥗 Nutricionista: Receta '{ingredients_found}' → "
        f"{len(selected)} ingredientes encontrados. {macro_text}"
    )
    return state


def _demo_logistics(state: CartState) -> CartState:
    """Agente Logístico: sustituye por Hacendado SÓLO dentro de la misma subcategoría."""
    final = []
    replaced = 0

    for product in state.selected_products:
        if product["brand"] == "Hacendado":
            final.append(product)
            continue

        # Buscar alternativa Hacendado en la MISMA subcategoría
        alternative = next(
            (p for p in state.available_products
             if p["brand"] == "Hacendado"
             and p["subcategory"] == product["subcategory"]
             and p not in final),
            None,
        )
        if alternative:
            final.append(alternative)
            replaced += 1
        else:
            final.append(product)

    state.selected_products = final
    pct = sum(1 for p in final if p["brand"] == "Hacendado") / max(len(final), 1) * 100
    state.agent_logs.append(
        f"📦 Logístico: {pct:.0f}% Hacendado (máximo margen). "
        f"{replaced} sustituciones realizadas."
    )
    return state


def _demo_financial(state: CartState) -> CartState:
    """Agente Financiero: ajusta al presupuesto protegiendo ingredientes esenciales."""
    # Marcar qué productos son esenciales (coinciden con los search_queries)
    def is_essential(p):
        name_l = p["name"].lower()
        cat_l = p["category"].lower()
        sub_l = p.get("subcategory", "").lower()
        return any(
            q.lower() in name_l or q.lower() in cat_l or q.lower() in sub_l
            for q in state.search_queries
        )

    # Ordenar: esenciales primero (no se eliminan), luego por precio asc
    state.selected_products.sort(
        key=lambda p: (0 if is_essential(p) else 1, p["price"])
    )

    final_cart = []
    running_total = 0.0

    for product in state.selected_products:
        if running_total + product["price"] <= state.budget:
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
        search_queries=constraints.get("search_queries", []),
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
        search_queries=constraints.get("search_queries", []),
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
        
        # Calcular macros totales
        tkcal = tprot = tcarb = tfat = 0.0
        for p in state.selected_products:
            # unit_size suele venir en kg o L. Multiplicamos x10 para pasar de porción 100g al total
            factor = (p.get("unit_size", 0.0) or 0) * 10
            if factor == 0: factor = 1 # Fallback mínimo
            tkcal += p.get("kcal_100g", 0) * factor
            tprot += p.get("protein_100g", 0) * factor
            tcarb += p.get("carbs_100g", 0) * factor
            tfat +=  p.get("fat_100g", 0) * factor
            
        macro_text = f"[Kcal: {int(tkcal)} | Proteína: {int(tprot)}g | Carbs: {int(tcarb)}g | Grasas: {int(tfat)}g]"
        state.agent_logs.append(f"🥗 Nutricionista: {data.get('reasoning', '')} {macro_text}")
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
