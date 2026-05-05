"""
Módulo 2 — Muro Determinista (CSP).
Filtra productos eliminando absolutamente cualquier alérgeno declarado
y aplica restricciones de presupuesto.

Soporta tanto filtrado completo como filtrado de deltas incrementales.
"""

from .database import get_safe_products, get_all_products


def apply_filters(
    constraints: dict,
) -> list[dict]:
    """
    Aplica el muro determinista:
      1. Elimina productos con alérgenos prohibidos (filtrado absoluto).
      2. Filtra por categorías relevantes al tipo de comida.
      3. Ordena por relevancia (prioridad marca Hacendado).

    Args:
        constraints: dict con claves del LLM translator
            - allergens: list[str]
            - budget: float
            - meal_type: str
            - diet: str
            - people: int
    
    Returns:
        Lista de productos seguros y relevantes.
    """
    allergens = constraints.get("allergens", [])
    meal_type = constraints.get("meal_type", "general")
    diet = constraints.get("diet", "equilibrado")
    search_queries = constraints.get("search_queries", [])

    # ─── Paso 1: Filtrado absoluto de alérgenos ──────────
    safe_products = get_safe_products(allergens, search_queries)

    # ─── Paso 2: Filtrado por relevancia al tipo de comida ─
    category_map = {
        "desayuno": ["lácteos", "cereales", "panadería", "bebidas", "huevos", "dulces"],
        "comida":   ["carne", "pescado", "verduras", "cereales", "legumbres", "aceites", "condimentos", "conservas"],
        "cena":     ["carne", "pescado", "verduras", "huevos", "lácteos", "conservas", "aceites", "condimentos"],
        "general":  [],  # Todas las categorías
        "semanal":  [],  # Todas las categorías
    }

    relevant_categories = category_map.get(meal_type, [])

    if relevant_categories:
        # Priorizar productos de categorías relevantes, sin excluir el resto
        def relevance_score(product: dict) -> int:
            score = 0
            if product["category"] in relevant_categories:
                score += 10
            if product["brand"] == "Hacendado":
                score += 5  # Priorizar marca blanca (más margen)
            return score

        safe_products.sort(key=relevance_score, reverse=True)
    else:
        # Ordenar por marca Hacendado primero
        safe_products.sort(
            key=lambda p: (0 if p["brand"] == "Hacendado" else 1, p["price"])
        )

    # ─── Paso 3: Filtrado por dieta ──────────────────────
    if "vegetariano" in diet.lower() or "vegano" in diet.lower():
        safe_products = [
            p for p in safe_products
            if p["category"] not in ("carne", "pescado", "marisco")
        ]
    if "vegano" in diet.lower():
        safe_products = [
            p for p in safe_products
            if p["category"] not in ("lácteos", "huevos")
        ]
    if "proteína" in diet.lower() or "proteina" in diet.lower():
        safe_products.sort(key=lambda p: p.get("protein_100g", 0), reverse=True)

    return safe_products


def apply_delta_filters(
    current_cart: list[dict],
    delta: dict,
    constraints: dict,
) -> tuple[list[dict], list[dict], list[int]]:
    """
    Aplica un cambio incremental sobre el carrito existente.
    El muro CSP sigue siendo ABSOLUTO: cualquier producto nuevo
    pasa por el filtro de alérgenos antes de entrar.

    Args:
        current_cart: Lista de productos actualmente en el carrito
        delta: dict con claves:
            - add_queries: list[str] — ingredientes a buscar y añadir
            - remove_queries: list[str] — ingredientes a quitar del carrito
            - modify: list[dict] — sustituciones [{"from": "...", "to": "..."}]
        constraints: dict con allergens, diet, budget, etc.

    Returns:
        (carrito_actualizado, productos_añadidos, ids_eliminados)
    """
    allergens = constraints.get("allergens", [])
    diet = constraints.get("diet", "equilibrado")

    updated_cart = list(current_cart)
    added_products = []
    removed_ids = []

    # ─── 1. Procesar eliminaciones ───────────────────────
    remove_queries = delta.get("remove_queries", [])
    for query in remove_queries:
        query_lower = query.lower()
        to_remove = []
        for p in updated_cart:
            name_lower = p["name"].lower()
            sub_lower = p.get("subcategory", "").lower()
            if query_lower in name_lower or query_lower in sub_lower:
                to_remove.append(p)
        for p in to_remove:
            removed_ids.append(p["id"])
            updated_cart.remove(p)

    # ─── 2. Procesar sustituciones (modify) ──────────────
    modifications = delta.get("modify", [])
    for mod in modifications:
        from_query = mod.get("from", "").lower()
        to_query = mod.get("to", "")

        # Quitar el producto viejo
        for p in list(updated_cart):
            name_lower = p["name"].lower()
            sub_lower = p.get("subcategory", "").lower()
            if from_query in name_lower or from_query in sub_lower:
                removed_ids.append(p["id"])
                updated_cart.remove(p)
                break

        # Buscar el producto nuevo (con filtro de alérgenos)
        new_products = get_safe_products(allergens, [to_query])
        # Filtrar por dieta
        new_products = _filter_by_diet(new_products, diet)

        if new_products:
            # Tomar el mejor candidato (Hacendado primero, precio más bajo)
            new_products.sort(
                key=lambda p: (0 if p["brand"] == "Hacendado" else 1, p["price"])
            )
            best = new_products[0]
            # No añadir duplicados
            if best["id"] not in {p["id"] for p in updated_cart}:
                updated_cart.append(best)
                added_products.append(best)

    # ─── 3. Procesar adiciones ───────────────────────────
    add_queries = delta.get("add_queries", [])
    current_ids = {p["id"] for p in updated_cart}

    for query in add_queries:
        # Buscar productos seguros (sin alérgenos prohibidos)
        safe = get_safe_products(allergens, [query])
        safe = _filter_by_diet(safe, diet)

        if safe:
            # Tomar el mejor candidato
            safe.sort(
                key=lambda p: (0 if p["brand"] == "Hacendado" else 1, p["price"])
            )
            for candidate in safe:
                if candidate["id"] not in current_ids:
                    updated_cart.append(candidate)
                    added_products.append(candidate)
                    current_ids.add(candidate["id"])
                    break

    return updated_cart, added_products, removed_ids


def _filter_by_diet(products: list[dict], diet: str) -> list[dict]:
    """Filtra productos según la dieta del usuario."""
    if "vegetariano" in diet.lower() or "vegano" in diet.lower():
        products = [
            p for p in products
            if p["category"] not in ("carne", "pescado", "marisco")
        ]
    if "vegano" in diet.lower():
        products = [
            p for p in products
            if p["category"] not in ("lácteos", "huevos")
        ]
    return products
