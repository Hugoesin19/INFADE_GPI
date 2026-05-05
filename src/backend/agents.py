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
    """
    Agente Nutricionista: busca exactamente 1 producto por cada ingrediente.
    Los search_queries vienen del mapa de recetas del translator (ej: "espaguetis",
    "carne picada", "tomate frito", "cebolla", "ajo", "aceite de oliva", "sal").
    """
    selected = []
    used_ids = set()
    used_subcategories = set()

    def _find_best(keyword: str) -> dict | None:
        """Encuentra el mejor producto para un ingrediente con scoring de relevancia."""
        candidates = []
        kw = keyword.lower()
        kw_words = set(kw.split())

        for p in state.available_products:
            if p["id"] in used_ids:
                continue

            name_l = p["name"].lower()
            sub_l = p.get("subcategory", "").lower()

            # Verificar si el producto tiene relación con el keyword
            # Se busca en nombre y subcategoría
            match = False
            score = 0

            # Coincidencia exacta o substring en nombre
            if kw in name_l:
                match = True
                # Bonus si el nombre empieza con el keyword
                if name_l.startswith(kw):
                    score += 100
                else:
                    score += 70
            # Alguna de las palabras clave está en el nombre
            elif kw_words and any(w in name_l for w in kw_words if len(w) >= 3):
                match = True
                # Cuántas palabras del keyword coinciden
                matching_words = sum(1 for w in kw_words if w in name_l and len(w) >= 3)
                score += 40 + (matching_words * 15)
            # Subcategoría contiene el keyword
            elif kw in sub_l:
                match = True
                score += 50

            if not match:
                continue

            # Penalizar si ya tenemos algo de esa subcategoría (evitar duplicados)
            if sub_l and sub_l in used_subcategories:
                score -= 30

            # Bonus Hacendado (más margen)
            if p["brand"] == "Hacendado":
                score += 10

            # Bonus menor precio (priorizar economía)
            score += max(0, 10 - int(p["price"]))

            candidates.append((score, p["price"], p))

        if not candidates:
            return None

        # Mayor score primero, luego precio más bajo
        candidates.sort(key=lambda x: (-x[0], x[1]))
        return candidates[0][2]

    # 1. Buscar exactamente 1 producto por cada ingrediente de la receta
    for q in state.search_queries:
        best = _find_best(q)
        if best:
            selected.append(best)
            used_ids.add(best["id"])
            sub = best.get("subcategory", "").lower()
            if sub:
                used_subcategories.add(sub)

    # 2. Fallback: si no hay queries (no se reconoció receta), selección general
    if not selected and not state.search_queries:
        base_cats = {"Carne", "Arroz, legumbres y pasta", "Fruta y verdura",
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
    recipe_name = state.notes or "general"
    state.agent_logs.append(
        f"🥗 Nutricionista: Receta '{recipe_name}' → "
        f"{len(selected)} ingredientes seleccionados. {macro_text}"
    )
    return state


def _demo_logistics(state: CartState) -> CartState:
    """
    Agente Logístico:
      1. Sustituye por Hacendado en la misma subcategoría cuando es posible.
      2. Prioriza productos con menor days_to_expiry (reducción desperdicio).
    """
    final = []
    replaced = 0
    waste_saved = 0

    for product in state.selected_products:
        # ── Sustitución por Hacendado ─────────────────────
        if product["brand"] != "Hacendado":
            alternative = None
            best_expiry = 9999

            for p in state.available_products:
                if (p["brand"] == "Hacendado"
                        and p["subcategory"] == product["subcategory"]
                        and p not in final
                        and p["id"] != product["id"]):
                    # Preferir la alternativa con menor caducidad (reduce desperdicio)
                    expiry = p.get("days_to_expiry", 180)
                    if alternative is None or expiry < best_expiry:
                        alternative = p
                        best_expiry = expiry

            if alternative:
                final.append(alternative)
                replaced += 1
                continue

        # ── Dentro de Hacendado: priorizar caducidad próxima ─
        # Si hay un producto equivalente (misma subcategoría) que caduca antes, sustituir
        product_expiry = product.get("days_to_expiry", 180)
        shorter_expiry = None

        for p in state.available_products:
            if (p["subcategory"] == product["subcategory"]
                    and p["brand"] == product["brand"]
                    and p["id"] != product["id"]
                    and p not in final):
                p_expiry = p.get("days_to_expiry", 180)
                if p_expiry < product_expiry:
                    if shorter_expiry is None or p_expiry < shorter_expiry.get("days_to_expiry", 180):
                        shorter_expiry = p

        if shorter_expiry:
            final.append(shorter_expiry)
            waste_saved += 1
        else:
            final.append(product)

    state.selected_products = final
    pct = sum(1 for p in final if p["brand"] == "Hacendado") / max(len(final), 1) * 100

    # Calcular días promedio de caducidad de la cesta
    avg_expiry = sum(p.get("days_to_expiry", 180) for p in final) / max(len(final), 1)

    log_parts = [f"📦 Logístico: {pct:.0f}% Hacendado (máximo margen)."]
    if replaced:
        log_parts.append(f"{replaced} sustituciones de marca.")
    if waste_saved:
        log_parts.append(f"{waste_saved} productos sustituidos por cercanía de caducidad.")
    log_parts.append(f"Caducidad media: {avg_expiry:.0f} días.")

    state.agent_logs.append(" ".join(log_parts))
    return state


def _demo_financial(state: CartState) -> CartState:
    """
    Agente Financiero:
      1. Asegura que los ingredientes esenciales caben en el presupuesto.
      2. Si queda margen, añade complementos lógicos (nunca relleno aleatorio).
      3. Si no hay margen suficiente, recorta los menos esenciales.
    """
    # ── Fase 1: Calcular el coste de la receta base ──────
    base_total = sum(p["price"] for p in state.selected_products)

    if base_total <= state.budget:
        # Todo cabe — mantener la receta completa
        final_cart = list(state.selected_products)
        running_total = base_total
    else:
        # No cabe todo — recortar los más caros no esenciales
        # Los primeros ingredientes en search_queries son más importantes
        def essentiality(p):
            name_l = p["name"].lower()
            for i, q in enumerate(state.search_queries):
                if q.lower() in name_l:
                    return i  # Más esencial = índice más bajo
            return 999  # No esencial

        sorted_products = sorted(state.selected_products, key=lambda p: essentiality(p))
        final_cart = []
        running_total = 0.0
        for product in sorted_products:
            if running_total + product["price"] <= state.budget:
                final_cart.append(product)
                running_total += product["price"]

    # ── Fase 2: Complementos lógicos si hay margen ───────
    remaining = state.budget - running_total
    added_complements = []

    if remaining >= 0.50:
        # Complementos según tipo de comida. Solo añadimos lo que tenga sentido.
        complements = _get_smart_complements(state.meal_type, state.selected_products)

        for complement_query in complements:
            if remaining < 0.50:
                break
            # Buscar el producto más barato que coincida
            best = None
            for p in state.available_products:
                if p["id"] in {x["id"] for x in final_cart}:
                    continue
                name_l = p["name"].lower()
                if complement_query.lower() in name_l:
                    if best is None or p["price"] < best["price"]:
                        best = p

            if best and best["price"] <= remaining:
                final_cart.append(best)
                remaining -= best["price"]
                running_total += best["price"]
                added_complements.append(best["name"])

    state.selected_products = final_cart
    state.total = round(running_total, 2)

    log = f"💰 Financiero: Cesta final {state.total}€ / {state.budget}€ presupuesto."
    if added_complements:
        log += f" Complementos añadidos: {', '.join(added_complements)}."
    log += f" Ahorro: {state.budget - state.total:.2f}€."

    state.agent_logs.append(log)
    return state


def _get_smart_complements(meal_type: str, current_products: list[dict]) -> list[str]:
    """
    Devuelve una lista de complementos lógicos según el tipo de comida,
    excluyendo categorías ya presentes en la cesta.
    """
    current_cats = {p.get("category", "").lower() for p in current_products}
    current_subs = {p.get("subcategory", "").lower() for p in current_products}

    # Complementos por tipo de comida (solo si no están ya en la cesta)
    complements = []

    if meal_type in ("comida", "cena"):
        if "pan" not in current_subs and "pan de molde" not in current_subs:
            complements.append("barra de pan")
        if "agua" not in " ".join(p["name"].lower() for p in current_products):
            complements.append("agua mineral")

    elif meal_type == "desayuno":
        if "zumo" not in " ".join(p["name"].lower() for p in current_products):
            complements.append("zumo de naranja")

    return complements


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


# ═══════════════════════════════════════════════════════════
#  DELTA AGENTS — Para el flujo conversacional de Mercadín
# ═══════════════════════════════════════════════════════════

def run_agents_delta(
    current_cart: list[dict],
    new_products: list[dict],
    removed_ids: list[int],
    constraints: dict,
) -> CartState:
    """
    Ejecuta los agentes SOLO sobre los productos afectados por el delta.
    Los productos existentes no afectados se mantienen intactos.

    Args:
        current_cart: Productos actualmente en el carrito
        new_products: Productos nuevos a añadir
        removed_ids: IDs de productos a eliminar
        constraints: Constraints acumuladas de la sesión
    """
    # 1. Filtrar el carrito actual (quitar eliminados)
    filtered_cart = [p for p in current_cart if p["id"] not in set(removed_ids)]

    # 2. Combinar con productos nuevos
    combined = filtered_cart + new_products

    # 3. Crear estado para los agentes
    state = CartState(
        available_products=combined + new_products,  # Pool disponible
        selected_products=combined,
        budget=constraints.get("budget", 25.0),
        people=constraints.get("people", 2),
        diet=constraints.get("diet", "equilibrado"),
        meal_type=constraints.get("meal_type", "general"),
        notes=constraints.get("notes", ""),
        search_queries=constraints.get("search_queries", []),
    )

    # 4. Solo ejecutar logístico y financiero (nutricionista ya seleccionó via CSP delta)
    state = _demo_logistics(state)
    state = _demo_financial(state)

    return state
