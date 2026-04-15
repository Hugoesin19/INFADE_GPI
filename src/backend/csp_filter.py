"""
Módulo 2 — Muro Determinista (CSP).
Filtra productos eliminando absolutamente cualquier alérgeno declarado
y aplica restricciones de presupuesto.
"""

from .database import get_safe_products


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
