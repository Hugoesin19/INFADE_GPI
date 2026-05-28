"""
Módulo 2 — Muro Determinista (CSP).
Filtra productos eliminando absolutamente cualquier alérgeno declarado
y aplica restricciones de presupuesto.

Incluye:
  - Mapa de alérgenos por keywords (no depende de datos de BD)
  - Filtrado absoluto pre-selección
  - Validación post-selección con sustitución automática

Soporta tanto filtrado completo como filtrado de deltas incrementales.
"""

import re
from .database import get_safe_products, get_all_products, search_products_smart


# ══════════════════════════════════════════════════════════════
#  MURO DE ALÉRGENOS POR KEYWORDS
#  Los datos de allergens en la BD están mayormente vacíos,
#  así que usamos un mapa determinista basado en el nombre del producto.
# ══════════════════════════════════════════════════════════════

ALLERGEN_KEYWORD_MAP = {
    "gluten": {
        "keywords": [
            "pan ", "pan de", "barra de pan", "chapata", "baguette", "hogaza",
            "harina", "trigo", "espagueti", "spaghetti", "macarron", "pasta ",
            "pasta penne", "fideo", "tallarín", "lasaña", "canelón", "ravioli",
            "pizza", "masa de pizza", "tortita", "crepe", "galleta", "bizcocho",
            "magdalena", "croissant", "brioche", "churro", "donut", "rosquilla",
            "cereal", "muesli", "avena", "cuscús", "couscous", "panko",
            "empanada", "empanadilla", "croqueta", "rebozado", "cerveza",
            "pan de molde", "tostada", "sandwich", "wrap", "pita",
        ],
        "categories": ["panadería y pastelería"],
        "subcategories": ["pan", "bollería", "pasta", "galletas", "cereales"],
    },
    "lactosa": {
        "keywords": [
            "leche", "nata", "queso", "yogur", "mantequilla", "cuajada",
            "mozzarella", "parmesano", "manchego", "brie", "camembert",
            "emmental", "gouda", "cheddar", "requesón", "mascarpone",
            "bechamel", "flan", "natillas", "arroz con leche", "helado",
            "batido", "petit suisse", "kéfir", "crema de", "nata para cocinar",
            "queso rallado", "queso tierno", "queso fresco", "queso curado",
        ],
        "categories": ["postres y yogures"],
        "subcategories": ["leche", "quesos", "yogures", "mantequilla", "nata"],
    },
    "huevo": {
        "keywords": [
            "huevo", "huevos", "tortilla", "mayonesa", "merengue",
            "bizcocho", "magdalena", "flan", "natillas", "brioche",
            "pasta al huevo", "croqueta",
        ],
        "categories": [],
        "subcategories": ["huevos"],
    },
    "frutos_secos": {
        "keywords": [
            "almendra", "avellana", "nuez", "nueces", "cacahuete", "pistacho",
            "anacardo", "castaña", "piñón", "piñones", "turrón", "mazapán",
            "praline", "praliné", "manteca de cacahuete", "crema de cacahuete",
            "frutos secos", "mix de frutos",
        ],
        "categories": [],
        "subcategories": ["frutos secos"],
    },
    "crustáceos": {
        "keywords": [
            "gamba", "gambas", "langostino", "langostinos", "bogavante",
            "cangrejo", "centollo", "cigala", "carabinero", "marisco",
            "paella de marisco", "sopa de marisco", "cóctel de marisco",
            "surimi",
        ],
        "categories": [],
        "subcategories": ["marisco", "crustáceos"],
    },
    "pescado": {
        "keywords": [
            "salmón", "salmon", "merluza", "bacalao", "atún", "atun",
            "sardina", "anchoa", "boquerón", "boqueron", "trucha",
            "dorada", "lubina", "rape", "lenguado", "pez espada",
            "caballa", "jurel", "rodaballo", "calamar", "sepia",
            "pulpo", "mejillón", "mejillon", "almeja", "berberecho",
            "surimi", "palitos de cangrejo",
        ],
        "categories": ["marisco y pescado"],
        "subcategories": ["pescado", "pescado fresco", "conservas de pescado"],
    },
}


def _product_has_allergen(product: dict, allergen: str) -> bool:
    """
    Determina si un producto contiene un alérgeno dado,
    usando TANTO los datos de la BD como el mapa de keywords.
    """
    # 1. Comprobar campo allergens de la BD (si existe)
    db_allergens = product.get("allergens", [])
    if isinstance(db_allergens, list) and allergen in db_allergens:
        return True

    # 2. Comprobar por keywords en nombre del producto
    allergen_info = ALLERGEN_KEYWORD_MAP.get(allergen, {})
    name_lower = product.get("name", "").lower()
    
    # Si el nombre del producto indica explícitamente "sin [alérgeno]",
    # ignoramos el resto de heurísticas por palabra clave.
    if f"sin {allergen}" in name_lower:
        return False
        
    cat_lower = product.get("category", "").lower()
    sub_lower = product.get("subcategory", "").lower()

    # Comprobar keywords
    for keyword in allergen_info.get("keywords", []):
        if keyword in name_lower:
            return True

    # Comprobar categorías
    for cat in allergen_info.get("categories", []):
        if cat == cat_lower:
            return True

    # Comprobar subcategorías
    for sub in allergen_info.get("subcategories", []):
        if sub == sub_lower:
            return True

    return False


def _product_is_safe(product: dict, excluded_allergens: list[str]) -> bool:
    """Devuelve True si el producto NO contiene ninguno de los alérgenos excluidos."""
    for allergen in excluded_allergens:
        if _product_has_allergen(product, allergen):
            return False
    return True


# ══════════════════════════════════════════════════════════════
#  FILTRADO PRE-SELECCIÓN
# ══════════════════════════════════════════════════════════════

def apply_filters(
    constraints: dict,
) -> list[dict]:
    """
    Aplica el muro determinista:
      1. Elimina productos con alérgenos prohibidos (filtrado ABSOLUTO por keywords + BD).
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

    # ─── Paso 1: Obtener productos base (filtrado BD + keywords search) ──
    all_products = get_all_products(search_queries) if search_queries else get_all_products()

    # ─── Paso 2: Filtrado ABSOLUTO de alérgenos (keyword-based) ──────────
    if allergens:
        safe_products = [p for p in all_products if _product_is_safe(p, allergens)]
        filtered_count = len(all_products) - len(safe_products)
        if filtered_count > 0:
            print(f"[CSP] Muro de alérgenos: {filtered_count} productos eliminados por {allergens}")
    else:
        safe_products = all_products

    # ─── Paso 3: Filtrado por relevancia al tipo de comida ─
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

    # ─── Paso 4: Filtrado por dieta ──────────────────────
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


# ══════════════════════════════════════════════════════════════
#  VALIDACIÓN POST-SELECCIÓN (después de los agentes)
# ══════════════════════════════════════════════════════════════

def validate_cart_allergens(
    cart: list[dict],
    excluded_allergens: list[str],
    available_products: list[dict],
) -> tuple[list[dict], list[str]]:
    """
    Validación FINAL del carrito contra alérgenos.
    Se ejecuta DESPUÉS de que los agentes seleccionen productos.
    
    Si un producto viola el muro, se elimina y se intenta sustituir
    por un producto seguro de la misma subcategoría.
    
    Args:
        cart: Carrito actual de productos seleccionados
        excluded_allergens: Lista de alérgenos a excluir
        available_products: Pool de productos disponibles para sustitución
    
    Returns:
        (carrito_validado, logs_de_cambios)
    """
    if not excluded_allergens:
        return cart, []

    validated_cart = []
    logs = []
    cart_ids = set()

    for product in cart:
        if _product_is_safe(product, excluded_allergens):
            validated_cart.append(product)
            cart_ids.add(product["id"])
        else:
            # Producto INSEGURO — buscar sustituto
            offending = [a for a in excluded_allergens if _product_has_allergen(product, a)]
            
            substitute = _find_safe_substitute(
                product, excluded_allergens, available_products, cart_ids
            )
            
            if substitute:
                validated_cart.append(substitute)
                cart_ids.add(substitute["id"])
                logs.append(
                    f"⚠️ CSP: '{product['name']}' contiene {', '.join(offending)} → "
                    f"Sustituido por '{substitute['name']}'"
                )
            else:
                logs.append(
                    f"🚫 CSP: '{product['name']}' contiene {', '.join(offending)} → "
                    f"Eliminado (sin sustituto seguro)"
                )

    if logs:
        print(f"[CSP] Validación post-agente: {len(logs)} cambios")
        for log in logs:
            print(f"  {log}")

    return validated_cart, logs


def _find_safe_substitute(
    original: dict,
    excluded_allergens: list[str],
    available_products: list[dict],
    used_ids: set,
) -> dict | None:
    """
    Busca un producto sustituto seguro en la misma subcategoría.
    Prioriza: misma subcategoría > misma categoría > búsqueda por nombre.
    """
    sub = original.get("subcategory", "").lower()
    cat = original.get("category", "").lower()
    
    candidates = []
    
    for p in available_products:
        if p["id"] in used_ids:
            continue
        if not _product_is_safe(p, excluded_allergens):
            continue
        
        # Scoring de similitud
        score = 0
        p_sub = p.get("subcategory", "").lower()
        p_cat = p.get("category", "").lower()
        
        if p_sub == sub and sub:
            score = 100
        elif p_cat == cat and cat:
            score = 50
        else:
            continue  # Solo sustituir dentro de categoría/subcategoría similar
        
        # Bonus Hacendado
        if p["brand"] == "Hacendado":
            score += 10
        
        # Penalizar diferencia de precio excesiva
        price_diff = abs(p["price"] - original["price"])
        score -= int(price_diff * 5)
        
        candidates.append((score, p["price"], p))
    
    if not candidates:
        return None
    
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[0][2]


# ══════════════════════════════════════════════════════════════
#  FILTRADO DELTA INCREMENTAL
# ══════════════════════════════════════════════════════════════

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

        # Quitar el producto viejo y guardarlo por si falla la búsqueda del nuevo
        removed_this_mod = None
        for p in list(updated_cart):
            name_lower = p["name"].lower()
            sub_lower = p.get("subcategory", "").lower()
            if from_query in name_lower or from_query in sub_lower:
                removed_this_mod = p
                removed_ids.append(p["id"])
                updated_cart.remove(p)
                break

        # Buscar el producto nuevo (con filtro de alérgenos por keywords)
        new_candidates = search_products_smart(to_query, limit=10)
        # Filtrar por alérgenos usando el muro de keywords
        new_products = [p for p in new_candidates if _product_is_safe(p, allergens)]
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
        else:
            # Si no se encontró el producto de sustitución, restaurar el original
            if removed_this_mod:
                removed_ids.remove(removed_this_mod["id"])
                updated_cart.append(removed_this_mod)

    # ─── 3. Procesar adiciones ───────────────────────────
    add_queries = delta.get("add_queries", [])
    current_ids = {p["id"] for p in updated_cart}

    for query in add_queries:
        # Buscar productos y filtrar por alérgenos con el muro de keywords
        candidates = search_products_smart(query, limit=10)
        safe = [p for p in candidates if _product_is_safe(p, allergens)]
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

