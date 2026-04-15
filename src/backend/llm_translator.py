"""
Módulo 1 — Traductor Multimodal (LLM).
Extrae variables estructuradas desde lenguaje natural usando Gemini.
"""

import json
import re
from typing import Any

from .config import GEMINI_API_KEY, GEMINI_MODEL, DEMO_MODE

# ── Prompt de sistema ─────────────────────────────────────

SYSTEM_PROMPT = """Eres un asistente de Mercadona España. Tu trabajo es extraer variables
estructuradas desde la petición del usuario para generar una cesta de la compra.

Devuelve ÚNICAMENTE un JSON válido con estos campos exactos (sin texto adicional):
{
  "budget": <número en euros, float. Si no se indica, usa 25.0>,
  "people": <número de personas, int. Si no se indica, usa 2>,
  "allergens": <lista de alérgenos a excluir. Posibles: "gluten", "lactosa", "huevo", "frutos_secos", "crustáceos", "pescado". Lista vacía si ninguno>,
  "diet": <descripción corta de la dieta/preferencia, string. Ej: "alta proteína", "vegetariano", "equilibrado". Si no se indica, usa "equilibrado">,
  "meal_type": <tipo de comida, string. Ej: "desayuno", "comida", "cena", "semanal", "general". Si no se indica, usa "general">,
  "search_queries": <lista de palabras clave para buscar productos en la base de datos de Mercadona que sirvan para la comida solicitada. Ej: ["arroz", "carne", "verdura"] para una paella>,
  "notes": <cualquier otro detalle relevante, string. Vacío si no hay>
}

Responde SOLO con el JSON, sin markdown, sin explicaciones."""

# ── Respuesta demo ────────────────────────────────────────

DEMO_RESPONSE = {
    "budget": 15.0,
    "people": 4,
    "allergens": [],
    "diet": "equilibrado",
    "meal_type": "comida",
    "notes": "paella",
}


# ══════════════════════════════════════════════════════════════
#  MAPA DE RECETAS — el corazón del modo demo
# ══════════════════════════════════════════════════════════════
# Cada clave es un set de sinónimos que activan esa receta.
# Los ingredientes usan palabras que coinciden con la BD demo.

_RECIPE_DB = [
    # ── Arroces ───────────────────────────────────────────
    {
        "names": {"paella", "paella valenciana", "arroz con pollo"},
        "meal_type": "comida",
        "ingredients": ["arroz redondo", "muslos de pollo", "judías verdes", "tomate", "aceite de oliva virgen", "azafrán", "sal"],
    },
    {
        "names": {"arroz a banda", "arroz con marisco"},
        "meal_type": "comida",
        "ingredients": ["arroz redondo", "gambas", "caldo", "tomate", "aceite de oliva virgen", "azafrán", "ajo"],
    },
    # ── Pastas ────────────────────────────────────────────
    {
        "names": {"spaghetti", "spaguetti", "sphaghetti", "espagueti", "espaguetis",
                  "pasta boloñesa", "boloñesa", "bolognesa", "spaghetti bolognese"},
        "meal_type": "comida",
        "ingredients": ["espaguetis", "carne picada", "tomate frito", "cebolla", "ajo", "aceite de oliva", "sal"],
    },
    {
        "names": {"carbonara", "pasta carbonara", "espaguetis carbonara"},
        "meal_type": "comida",
        "ingredients": ["espaguetis", "bacon", "huevos", "queso rallado", "pimienta negra", "aceite de oliva"],
    },
    {
        "names": {"macarrones", "macarrones con tomate", "macarrones boloñesa"},
        "meal_type": "comida",
        "ingredients": ["macarrones", "carne picada", "tomate frito", "queso rallado", "cebolla", "aceite de oliva", "sal"],
    },
    {
        "names": {"pasta pesto", "penne pesto"},
        "meal_type": "comida",
        "ingredients": ["pasta penne", "salsa pesto", "queso rallado", "aceite de oliva"],
    },
    {
        "names": {"lasaña", "lasagna"},
        "meal_type": "comida",
        "ingredients": ["lasaña boloñesa"],  # Plato preparado en la BD
    },
    # ── Huevos ────────────────────────────────────────────
    {
        "names": {"tortilla", "tortilla española", "tortilla de patatas", "tortilla de patata"},
        "meal_type": "comida",
        "ingredients": ["huevos", "patatas selección", "cebolla", "aceite de oliva", "sal"],
    },
    {
        "names": {"huevos fritos", "huevos con patatas", "huevos rotos"},
        "meal_type": "comida",
        "ingredients": ["huevos", "patatas selección", "jamón serrano", "aceite de oliva", "sal"],
    },
    # ── Ensaladas ─────────────────────────────────────────
    {
        "names": {"ensalada", "ensalada mixta", "ensalada verde"},
        "meal_type": "comida",
        "ingredients": ["lechuga", "tomates pera", "atún", "maíz dulce", "aceite de oliva virgen", "vinagre"],
    },
    {
        "names": {"ensalada cesar", "ensalada césar", "cesar", "césar"},
        "meal_type": "comida",
        "ingredients": ["lechuga romana", "pechuga de pollo", "queso rallado", "pan", "aceite de oliva virgen"],
    },
    # ── Sopas y caldos ────────────────────────────────────
    {
        "names": {"sopa", "sopa de pollo", "sopa de fideos"},
        "meal_type": "cena",
        "ingredients": ["fideos", "caldo de pollo", "zanahoria", "pechuga de pollo", "sal"],
    },
    {
        "names": {"gazpacho"},
        "meal_type": "comida",
        "ingredients": ["tomates pera", "pepino", "pimiento", "aceite de oliva virgen", "vinagre", "ajo", "sal"],
    },
    {
        "names": {"crema de calabaza", "crema de verduras"},
        "meal_type": "cena",
        "ingredients": ["crema de calabaza", "pan"],
    },
    # ── Legumbres ─────────────────────────────────────────
    {
        "names": {"lentejas", "lentejas estofadas"},
        "meal_type": "comida",
        "ingredients": ["lentejas", "chorizo", "patatas selección", "zanahoria", "cebolla", "aceite de oliva", "pimentón", "sal"],
    },
    {
        "names": {"cocido", "cocido madrileño"},
        "meal_type": "comida",
        "ingredients": ["garbanzos cocidos", "carne picada", "patatas selección", "zanahoria", "caldo", "fideos", "sal"],
    },
    {
        "names": {"alubias", "fabada", "judiones"},
        "meal_type": "comida",
        "ingredients": ["alubias", "chorizo", "cebolla", "aceite de oliva", "pimentón", "sal"],
    },
    # ── Carnes ────────────────────────────────────────────
    {
        "names": {"pollo asado", "pollo al horno"},
        "meal_type": "comida",
        "ingredients": ["muslos de pollo", "patatas selección", "cebolla", "aceite de oliva virgen", "sal", "pimienta negra"],
    },
    {
        "names": {"hamburguesa", "hamburguesas", "burger"},
        "meal_type": "comida",
        "ingredients": ["hamburguesas de vacuno", "pan de hamburguesa", "lechuga", "tomates pera", "queso tierno", "kétchup"],
    },
    {
        "names": {"filetes", "filetes de pollo", "pechuga", "pechuga a la plancha"},
        "meal_type": "comida",
        "ingredients": ["pechuga de pollo", "aceite de oliva", "lechuga", "tomates pera", "sal"],
    },
    {
        "names": {"costillas", "costillas al horno", "costillas barbacoa"},
        "meal_type": "comida",
        "ingredients": ["costillas de cerdo", "patatas selección", "aceite de oliva", "sal", "pimienta negra"],
    },
    # ── Pescados ──────────────────────────────────────────
    {
        "names": {"merluza", "merluza a la plancha", "merluza al horno"},
        "meal_type": "cena",
        "ingredients": ["merluza", "patatas", "aceite de oliva virgen", "limón", "sal"],
    },
    {
        "names": {"salmón", "salmón a la plancha", "salmón al horno"},
        "meal_type": "cena",
        "ingredients": ["salmón", "brócoli", "aceite de oliva virgen", "limón", "sal"],
    },
    # ── Bocadillos y rápidos ──────────────────────────────
    {
        "names": {"bocadillo", "bocadillos", "bocata"},
        "meal_type": "comida",
        "ingredients": ["panecillos", "jamón serrano", "queso tierno", "tomate"],
    },
    {
        "names": {"pizza"},
        "meal_type": "cena",
        "ingredients": ["masa de pizza", "tomate frito", "mozzarella", "jamón cocido", "aceite de oliva"],
    },
    {
        "names": {"sandwich", "sándwich"},
        "meal_type": "comida",
        "ingredients": ["pan de molde", "jamón cocido", "queso tierno", "lechuga", "tomate"],
    },
    {
        "names": {"croquetas"},
        "meal_type": "cena",
        "ingredients": ["croquetas de jamón", "lechuga", "tomate"],
    },
    # ── Desayunos / Meriendas ─────────────────────────────
    {
        "names": {"desayuno"},
        "meal_type": "desayuno",
        "ingredients": ["leche", "cereales", "pan de molde", "mermelada", "zumo de naranja"],
    },
    {
        "names": {"merienda"},
        "meal_type": "desayuno",
        "ingredients": ["pan de molde", "nocilla", "leche", "galletas"],
    },
    {
        "names": {"tostadas", "tostada"},
        "meal_type": "desayuno",
        "ingredients": ["pan", "aceite de oliva virgen", "tomate", "jamón serrano", "sal"],
    },
]


def translate_prompt(user_text: str) -> dict[str, Any]:
    """
    Traduce el texto libre del usuario a un dict estructurado.
    Si no hay API key, devuelve la respuesta demo.
    """
    print(f"DEBUG PROMPT: {user_text!r}")
    if DEMO_MODE:
        return _fallback_translate(user_text)

    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"{SYSTEM_PROMPT}\n\n--- Petición del usuario ---\n{user_text}",
        )

        # Extraer el JSON de la respuesta
        raw = response.text.strip()

        # Limpiar posibles bloques markdown ```json ... ```
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback si el LLM no devuelve JSON limpio
            result = _fallback_translate(user_text)

        return result

    except Exception as e:
        # Si la API key es inválida o nos pasamos de la cuota (429), fallback
        print(f"[LLM] Error al llamar a Gemini, usando modo demo: {e}")
        return _fallback_translate(user_text)


def _fallback_translate(user_text: str) -> dict[str, Any]:
    """
    Traductor determinista sin LLM.
    Extrae variables con regex y un mapa masivo de recetas.
    """
    text = user_text.lower().strip()

    result = {
        "budget": 25.0,
        "people": 2,
        "allergens": [],
        "diet": "equilibrado",
        "meal_type": "general",
        "search_queries": [],
        "notes": user_text,
    }

    # ── 1. Extraer presupuesto ────────────────────────────
    budget_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:euros|€|eur)", text)
    if budget_match:
        result["budget"] = float(budget_match.group(1).replace(",", "."))

    # ── 2. Extraer personas ───────────────────────────────
    # Probar varios patrones: "para 4 personas", "para 4", "4 personas", "de 3"
    people_patterns = [
        r"para\s+(\d+)\s*persona",
        r"(\d+)\s*persona",
        r"para\s+(\d+)(?:\s*,|\s*$|\s+\w)",
        r"de\s+(\d+)\s*(?:personas|comensales|gente)",
    ]
    for pattern in people_patterns:
        m = re.search(pattern, text)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 20:  # Rango razonable
                result["people"] = n
                break

    # ── 3. Extraer alérgenos ──────────────────────────────
    allergen_map = {
        "gluten": "gluten",
        "lactosa": "lactosa",
        "huevo": "huevo",
        "frutos secos": "frutos_secos",
        "frutos_secos": "frutos_secos",
        "cacahuete": "frutos_secos",
        "crustáceo": "crustáceos",
        "marisco": "crustáceos",
        "gamba": "crustáceos",
        "pescado": "pescado",
        "soja": "soja",
    }
    for keyword, allergen in allergen_map.items():
        if f"sin {keyword}" in text or f"no {keyword}" in text or f"libre de {keyword}" in text:
            if allergen not in result["allergens"]:
                result["allergens"].append(allergen)

    # ── 4. Extraer dieta ──────────────────────────────────
    if "prote" in text:
        result["diet"] = "alta proteína"
    elif "vegan" in text:
        result["diet"] = "vegano"
    elif "vegetarian" in text or "vegetariana" in text:
        result["diet"] = "vegetariano"
    elif "bajo en grasas" in text or "light" in text:
        result["diet"] = "bajo en grasas"

    # ── 5. Buscar receta en el mapa ───────────────────────
    matched_recipe = None
    for recipe in _RECIPE_DB:
        for name in recipe["names"]:
            if name in text:
                matched_recipe = recipe
                break
        if matched_recipe:
            break

    if matched_recipe:
        result["search_queries"] = list(matched_recipe["ingredients"])
        result["meal_type"] = matched_recipe["meal_type"]
        # Encontrar el nombre de la receta para notes
        for name in matched_recipe["names"]:
            if name in text:
                result["notes"] = name
                break
    else:
        # ── 6. Sin receta: extraer palabras de comida ─────
        _FOOD_VOCAB = {
            "arroz", "pollo", "carne", "pescado", "verdura", "fruta", "leche",
            "huevo", "huevos", "pan", "queso", "tomate", "lechuga", "patata",
            "patatas", "cebolla", "atún", "aceite", "pasta", "jamón", "yogur",
            "mantequilla", "cereales", "garbanzo", "lenteja", "lentejas",
            "maíz", "pimiento", "zanahoria", "pepino", "azúcar", "sal",
            "harina", "chorizo", "salchichón", "lomo", "salmón", "merluza",
            "gamba", "gambas", "pechuga", "muslo", "costilla", "costillas",
            "manzana", "plátano", "naranja", "fresa", "cerveza", "vino",
            "agua", "zumo", "café", "chocolate", "galleta", "galletas",
            "pizza", "hamburguesa", "hamburguesas", "fideos", "espagueti",
            "espaguetis", "macarrones", "vinagre", "mermelada", "brócoli",
            "calabacín", "champiñones", "espinacas", "aguacate", "bacon",
            "mozzarella", "albahaca", "perejil", "limón",
        }
        queries = []
        for word in text.split():
            w = word.strip(".,;:!?¿¡")
            if w in _FOOD_VOCAB:
                queries.append(w)
        result["search_queries"] = queries

    return result
