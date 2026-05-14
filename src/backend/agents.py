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
    brand_preference: str = "Hacendado"
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
    used_ids = {p["id"] for p in state.selected_products}
    used_subcategories = {p.get("subcategory", "").lower() for p in state.selected_products if p.get("subcategory")}

    def _find_best(keyword: str) -> dict | None:
        """Encuentra el mejor producto para un ingrediente con scoring de relevancia."""
        import unicodedata
        import re
        def normalize_str(s):
            s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
            s = s.lower()
            s = re.sub(r'\b(el|la|los|las|un|una|unos|unas|mi|mis)\b', '', s)
            return re.sub(r'\s+', ' ', s).strip()

        candidates = []
        kw = normalize_str(keyword)
        kw_words = set(kw.split())

        for p in state.available_products:
            if p["id"] in used_ids:
                continue

            name_l = normalize_str(p["name"])
            sub_l = normalize_str(p.get("subcategory", ""))
            name_words = set(name_l.split())

            match = False
            score = 0

            # 1. Coincidencia exacta del nombre completo
            if kw == name_l:
                match = True
                score = 500

            # 2. El nombre empieza exactamente con el query
            elif name_l.startswith(kw):
                match = True
                score = 300

            # 3. TODAS las palabras del query están en el nombre
            elif kw_words and len(kw_words) > 1 and kw_words.issubset(name_words):
                match = True
                score = 200 + (len(kw_words) * 20)

            # 4. El query completo es un substring del nombre
            elif kw in name_l:
                match = True
                score = 150

            # 5. Alguna de las palabras clave está en el nombre (como palabra exacta)
            elif kw_words and any(w in name_words for w in kw_words if len(w) >= 3):
                match = True
                matching_words = sum(1 for w in kw_words if w in name_words and len(w) >= 3)
                total_kw_words = max(len(kw_words), 1)
                score = 40 + (matching_words * 15)
                
                # Gran bonus si comparten la primera palabra (el sustantivo principal)
                kw_first = kw.split()[0] if kw.split() else ""
                name_first = name_l.split()[0] if name_l.split() else ""
                if kw_first == name_first and len(kw_first) >= 3:
                    score += 80

            # 6. Subcategoría contiene el keyword
            elif kw in sub_l:
                match = True
                score = 30

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

            # Penalizar nombres mucho más largos que el query (menos relevante)
            len_ratio = len(name_l) / max(len(kw), 1)
            if len_ratio > 4:
                score -= 10

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
    if not selected and not state.search_queries and not state.selected_products:
        base_cats = {"Carne", "Arroz, legumbres y pasta", "Fruta y verdura",
                     "Aceite, especias y salsas", "Huevos, leche y mantequilla"}
        for p in state.available_products:
            if p["category"] in base_cats and p["id"] not in used_ids:
                selected.append(p)
                used_ids.add(p["id"])
                if len(selected) >= 5:
                    break

    state.selected_products.extend(selected)

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
        # ── Sustitución por Marca Preferida ─────────────────────
        pref = state.brand_preference
        
        # Lógica para Hacendado
        if pref == "Hacendado" and product["brand"] != "Hacendado":
            alternative = None
            best_expiry = 9999
            for p in state.available_products:
                if (p["brand"] == "Hacendado"
                        and p["subcategory"] == product["subcategory"]
                        and p not in final
                        and p["id"] != product["id"]):
                    expiry = p.get("days_to_expiry", 180)
                    if alternative is None or expiry < best_expiry:
                        alternative = p
                        best_expiry = expiry
            if alternative:
                final.append(alternative)
                replaced += 1
                continue
                
        # Lógica para Marcas Premium
        elif pref == "Premium" and product["brand"] == "Hacendado":
            alternative = None
            for p in state.available_products:
                if (p["brand"] != "Hacendado"
                        and p["subcategory"] == product["subcategory"]
                        and p not in final
                        and p["id"] != product["id"]):
                    # Si hay varias alternativas premium, podemos coger cualquiera (la primera)
                    alternative = p
                    break
            if alternative:
                final.append(alternative)
                replaced += 1
                continue

        # ── Priorizar caducidad próxima dentro de la misma marca ─
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
    pct_hacendado = sum(1 for p in final if p["brand"] == "Hacendado") / max(len(final), 1) * 100
    pct_premium = 100 - pct_hacendado

    # Calcular días promedio de caducidad de la cesta
    avg_expiry = sum(p.get("days_to_expiry", 180) for p in final) / max(len(final), 1)

    pref_str = f"{pct_hacendado:.0f}% Hacendado" if state.brand_preference == "Hacendado" else f"{pct_premium:.0f}% Premium"
    log_parts = [f"📦 Logístico: Preferencia {state.brand_preference} aplicada ({pref_str})."]
    if replaced:
        log_parts.append(f"{replaced} sustituciones de marca.")
    if waste_saved:
        log_parts.append(f"{waste_saved} productos sustituidos por cercanía de caducidad.")
    log_parts.append(f"Caducidad media: {avg_expiry:.0f} días.")

    state.agent_logs.append(" ".join(log_parts))
    return state


def _demo_financial(state: CartState) -> CartState:
    """
    Agente Financiero — MAXIMIZADOR DE PRESUPUESTO:
      1. Asegura que los ingredientes esenciales caben en el presupuesto.
      2. Si queda margen, LLENA activamente con complementos inteligentes.
      3. Escala a las personas del hogar (más cantidad si más gente).
      4. Si no hay margen suficiente, recorta los menos esenciales.
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

    # ── Fase 2: Maximizar presupuesto con complementos inteligentes ──
    remaining = state.budget - running_total
    added_complements = []
    cart_ids = {p["id"] for p in final_cart}
    cart_names_lower = " ".join(p["name"].lower() for p in final_cart)
    cart_subs = {p.get("subcategory", "").lower() for p in final_cart}

    if remaining >= 0.50:
        # Obtener complementos priorizados por tipo de comida y personas
        complement_queries = _get_smart_complements(
            state.meal_type, final_cart, state.people, state.diet
        )

        for complement_query in complement_queries:
            if remaining < 0.50:
                break

            cq_lower = complement_query.lower()

            # Evitar duplicados por nombre
            if cq_lower in cart_names_lower:
                continue

            # Buscar el mejor producto que coincida (mejor relación calidad/precio)
            candidates = []
            for p in state.available_products:
                if p["id"] in cart_ids:
                    continue
                name_l = p["name"].lower()
                if cq_lower in name_l and p["price"] <= remaining:
                    # Score: priorizar valor nutricional por euro
                    protein_per_euro = (p.get("protein_100g", 0) or 0) / max(p["price"], 0.01)
                    brand_bonus = 5 if p["brand"] == state.brand_preference else 0
                    score = protein_per_euro + brand_bonus
                    candidates.append((score, p["price"], p))

            if candidates:
                candidates.sort(key=lambda x: (-x[0], x[1]))
                best = candidates[0][2]
                final_cart.append(best)
                cart_ids.add(best["id"])
                cart_names_lower += " " + best["name"].lower()
                remaining -= best["price"]
                running_total += best["price"]
                added_complements.append(best["name"])

    state.selected_products = final_cart
    state.total = round(running_total, 2)

    usage_pct = (state.total / state.budget * 100) if state.budget > 0 else 0
    log = f"💰 Financiero: Cesta {state.total}€ / {state.budget}€ ({usage_pct:.0f}% aprovechado)."
    if added_complements:
        log += f" Complementos: {', '.join(added_complements)}."
    if remaining > 0.50:
        log += f" Margen restante: {remaining:.2f}€."

    state.agent_logs.append(log)
    return state


def _get_smart_complements(
    meal_type: str,
    current_products: list[dict],
    people: int = 2,
    diet: str = "equilibrado",
) -> list[str]:
    """
    Devuelve una lista EXTENSA y priorizada de complementos lógicos
    según el tipo de comida, personas y dieta.
    Diseñado para maximizar el uso del presupuesto.
    """
    current_names = " ".join(p["name"].lower() for p in current_products)
    current_cats = {p.get("category", "").lower() for p in current_products}
    current_subs = {p.get("subcategory", "").lower() for p in current_products}

    complements = []

    # ─── Complementos universales (siempre útiles) ───────
    universal = [
        "agua mineral", "aceite de oliva", "sal",
    ]
    for u in universal:
        if u not in current_names:
            complements.append(u)

    # ─── Complementos por tipo de comida ─────────────────
    if meal_type in ("comida", "cena", "general", "semanal"):
        meal_complements = [
            # Básicos de cocina
            "cebolla", "ajo", "tomate", "pimiento",
            # Pan
            "barra de pan", "pan de molde",
            # Proteínas adicionales si quedan pocas
            "huevos",
            # Guarniciones
            "patatas", "arroz", "lechuga",
            # Frutas (postre natural)
            "manzana", "plátano", "naranja",
            # Bebidas
            "zumo de naranja", "cerveza",
            # Conservas útiles
            "tomate frito", "atún",
            # Lácteos básicos
            "leche", "yogur",
        ]
        complements.extend(meal_complements)

    elif meal_type == "desayuno":
        breakfast_complements = [
            "zumo de naranja", "cereales", "leche",
            "mermelada", "mantequilla", "yogur",
            "café", "galletas", "fruta",
            "pan de molde", "tostadas",
        ]
        complements.extend(breakfast_complements)

    # ─── Complementos por personas (escalar) ─────────────
    if people >= 4:
        # Para familias grandes, más básicos
        bulk_complements = [
            "arroz", "pasta", "patatas",
            "leche", "pan de molde", "aceite de oliva",
        ]
        for bc in bulk_complements:
            if bc not in complements:
                complements.append(bc)

    # ─── Complementos por dieta ──────────────────────────
    if "proteína" in diet.lower() or "proteina" in diet.lower():
        protein_complements = [
            "pechuga de pollo", "atún", "huevos",
            "yogur", "leche", "queso",
        ]
        # Poner al principio (más prioridad)
        complements = protein_complements + complements

    # Eliminar duplicados manteniendo orden
    seen = set()
    unique = []
    for c in complements:
        c_lower = c.lower()
        if c_lower not in seen and c_lower not in current_names:
            seen.add(c_lower)
            unique.append(c)

    return unique


def _demo_financial_conservative(state: CartState, add_complements: bool = True) -> CartState:
    """
    Agente Financiero para flujo conversacional delta.
    1. Recorta si excede presupuesto.
    2. Si queda margen significativo (>30% del presupuesto) y add_complements es True, sugiere
       complementos relevantes para maximizar el valor de la compra.
    """
    base_total = sum(p["price"] for p in state.selected_products)

    if base_total > state.budget:
        # No cabe todo — recortar los menos esenciales
        def essentiality(p):
            name_l = p["name"].lower()
            for i, q in enumerate(state.search_queries):
                if q.lower() in name_l:
                    return i
            return 999

        sorted_products = sorted(state.selected_products, key=lambda p: essentiality(p))
        final_cart = []
        running_total = 0.0
        removed = []
        for product in sorted_products:
            if running_total + product["price"] <= state.budget:
                final_cart.append(product)
                running_total += product["price"]
            else:
                removed.append(product["name"])

        state.selected_products = final_cart
        state.total = round(running_total, 2)

        log = f"💰 Financiero: Cesta ajustada a {state.total}€ / {state.budget}€."
        if removed:
            log += f" Eliminados por presupuesto: {', '.join(removed)}."
        state.agent_logs.append(log)
    else:
        running_total = base_total

        # Si queda más del 30% del presupuesto, intentar llenarlo
        remaining = state.budget - running_total
        usage_pct = (running_total / state.budget * 100) if state.budget > 0 else 100
        added_complements = []

        if add_complements and remaining >= 2.0 and usage_pct < 70:
            cart_ids = {p["id"] for p in state.selected_products}
            cart_names_lower = " ".join(p["name"].lower() for p in state.selected_products)

            complement_queries = _get_smart_complements(
                state.meal_type, state.selected_products, state.people, state.diet
            )

            for cq in complement_queries:
                if remaining < 0.50:
                    break
                cq_lower = cq.lower()
                if cq_lower in cart_names_lower:
                    continue

                best = None
                for p in state.available_products:
                    if p["id"] in cart_ids:
                        continue
                    if cq_lower in p["name"].lower() and p["price"] <= remaining:
                        if best is None or p["price"] < best["price"]:
                            best = p

                if best:
                    state.selected_products.append(best)
                    cart_ids.add(best["id"])
                    cart_names_lower += " " + best["name"].lower()
                    remaining -= best["price"]
                    running_total += best["price"]
                    added_complements.append(best["name"])

        state.total = round(running_total, 2)
        final_usage = (state.total / state.budget * 100) if state.budget > 0 else 100
        log = f"💰 Financiero: Cesta {state.total}€ / {state.budget}€ ({final_usage:.0f}% aprovechado). ✅"
        if added_complements:
            log += f" Complementos añadidos: {', '.join(added_complements)}."
        state.agent_logs.append(log)

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
        brand_preference=constraints.get("brand_preference", "Hacendado"),
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
        brand_preference=constraints.get("brand_preference", "Hacendado"),
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

    # 4. Supervisor
    state = _demo_supervisor(state)

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
    delta: dict,
    available_products: list[dict],
    constraints: dict,
) -> CartState:
    """
    Aplica acciones_delta sobre el carrito existente usando los agentes.
    El Agente Nutricionista busca los nuevos ingredientes sin duplicar.
    """
    state = CartState(
        available_products=available_products,
        selected_products=list(current_cart),
        budget=constraints.get("budget", 25.0),
        people=constraints.get("people", 2),
        diet=constraints.get("diet", "equilibrado"),
        meal_type=constraints.get("meal_type", "general"),
        notes=constraints.get("notes", ""),
        brand_preference=constraints.get("brand_preference", "Hacendado"),
        search_queries=delta.get("add_queries", []),
    )

    # Helper para quitar tildes
    import unicodedata
    import re
    def strip_accents_and_articles(s):
        s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
        s = s.lower()
        s = re.sub(r'\b(el|la|los|las|un|una|unos|unas|mi|mis)\b', '', s)
        return s.strip()

    # 1. Aplicar eliminaciones y modificaciones
    remove_queries = [strip_accents_and_articles(q) for q in delta.get("remove_queries", [])]
    modifications = delta.get("modify", [])
    
    updated_cart = []
    removed_ids = set()
    
    for p in state.selected_products:
        name_l = strip_accents_and_articles(p["name"])
        sub_l = strip_accents_and_articles(p.get("subcategory", ""))
        
        # Eliminar si coincide con remove_queries
        if any(q in name_l or q in sub_l for q in remove_queries):
            removed_ids.add(p["id"])
            continue
            
        # Eliminar si coincide con el "from" de una modificación
        modified = False
        for mod in modifications:
            from_q = strip_accents_and_articles(mod.get("from", ""))
            if from_q and (from_q in name_l or from_q in sub_l):
                removed_ids.add(p["id"])
                # Añadir el "to" a las queries a buscar
                to_q = mod.get("to", "")
                if to_q:
                    state.search_queries.append(to_q)
                modified = True
                break
                
        if not modified:
            updated_cart.append(p)
            
    state.selected_products = updated_cart

    # 2. Nutricionista busca los nuevos (add_queries + 'to' de modify)
    if state.search_queries:
        state = _demo_nutritionist(state)

    # 3. Financiero: NO recortar ingredientes de receta.
    #    El usuario pidió estos productos específicamente; cortarlos rompe la receta.
    #    Solo advertimos si se excede el presupuesto.
    total = sum(p["price"] for p in state.selected_products)
    state.total = round(total, 2)
    if total > state.budget:
        state.agent_logs.append(
            f"💰 Financiero: Cesta {state.total}€ supera el presupuesto de {state.budget}€. "
            f"Todos los ingredientes de la receta se han mantenido."
        )
    else:
        usage = (total / state.budget * 100) if state.budget > 0 else 100
        state.agent_logs.append(
            f"💰 Financiero: Cesta {state.total}€ / {state.budget}€ ({usage:.0f}% aprovechado). ✅"
        )

    # 4. Supervisor de Calidad: Verifica coherencia y audita la compra
    state = _demo_supervisor(state)

    return state


def _demo_supervisor(state: CartState) -> CartState:
    """
    Agente Supervisor de Calidad.
    Audita el carrito para asegurarse de que cumple estándares básicos:
    - Sin productos duplicados absolutos.
    - Presupuesto no rebasado gravemente.
    - Genera un sello de calidad final.
    """
    if not state.selected_products:
        return state

    # 1. Eliminar duplicados exactos por seguridad
    seen_ids = set()
    dedup = []
    for p in state.selected_products:
        if p["id"] not in seen_ids:
            seen_ids.add(p["id"])
            dedup.append(p)
    
    dups_removed = len(state.selected_products) - len(dedup)
    state.selected_products = dedup

    # 2. Verificar estado del presupuesto
    total = sum(p["price"] for p in state.selected_products)
    state.total = round(total, 2)
    
    status_msg = "✅ Todo en orden."
    if state.total > state.budget * 1.1:
        status_msg = "⚠️ Presupuesto ligeramente excedido por falta de alternativas baratas."

    log = f"👁️ Supervisor: Carrito auditado. {len(state.selected_products)} productos listos. {status_msg}"
    if dups_removed > 0:
        log += f" (Se han corregido {dups_removed} duplicados)."

    state.agent_logs.append(log)
    return state
