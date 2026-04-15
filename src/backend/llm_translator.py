"""
Módulo 1 — Traductor Multimodal (LLM).
Extrae variables estructuradas desde lenguaje natural usando Gemini.
"""

import json
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


def translate_prompt(user_text: str) -> dict[str, Any]:
    """
    Traduce el texto libre del usuario a un dict estructurado.
    Si no hay API key, devuelve la respuesta demo.
    """
    if DEMO_MODE:
        return DEMO_RESPONSE.copy()

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
            result = DEMO_RESPONSE.copy()
            result["notes"] = user_text

        return result

    except Exception as e:
        # Si la API key es inválida o nos pasamos de la cuota (429), fallback a demo
        print(f"[LLM] Error al llamar a Gemini, usando modo demo: {e}")
        fallback = DEMO_RESPONSE.copy()
        fallback["notes"] = user_text

        import re
        text = user_text.lower()

        # Extraer presupuesto
        budget_match = re.search(r"(\d+)\s*(euros|€)", text)
        if budget_match:
            fallback["budget"] = float(budget_match.group(1))

        # Extraer personas
        people_match = re.search(r"(\d+)\s*persona", text)
        if people_match:
            fallback["people"] = int(people_match.group(1))

        # Dieta
        if "prote" in text:
            fallback["diet"] = "alta proteína"
        elif "vegan" in text or "vegetariana" in text:
            fallback["diet"] = "vegetariano"

        # Recetas conocidas → ingredientes directos
        _RECIPE_MAP = {
            "paella":       ["arroz", "pollo", "verdura", "aceite", "azafrán"],
            "tortilla":     ["huevo", "patata", "aceite", "cebolla"],
            "ensalada":     ["lechuga", "tomate", "atún", "aceite", "maíz"],
            "pasta":        ["pasta", "tomate", "queso", "carne", "aceite"],
            "pizza":        ["pizza", "queso", "tomate"],
            "hamburguesa":  ["hamburguesa", "pan", "lechuga", "tomate", "queso"],
            "gazpacho":     ["tomate", "pepino", "pimiento", "aceite", "vinagre"],
            "cocido":       ["garbanzo", "carne", "verdura", "patata"],
            "lentejas":     ["lenteja", "chorizo", "patata", "zanahoria"],
            "macarrones":   ["pasta", "tomate", "carne", "queso"],
            "arroz":        ["arroz", "pollo", "verdura"],
            "pollo":        ["pollo", "patata", "aceite"],
            "sopa":         ["verdura", "fideos", "pollo"],
            "bocadillo":    ["pan", "jamón", "queso"],
            "desayuno":     ["leche", "cereales", "pan", "mermelada", "mantequilla"],
        }

        queries = []
        for recipe, ingredients in _RECIPE_MAP.items():
            if recipe in text:
                queries.extend(ingredients)
                fallback["notes"] = recipe
                break

        # Si no coincidió ninguna receta, extraer sólo palabras de comida
        if not queries:
            _FOOD_VOCAB = {
                "arroz", "pollo", "carne", "pescado", "verdura", "fruta", "leche",
                "huevo", "pan", "queso", "tomate", "lechuga", "patata", "cebolla",
                "atún", "aceite", "pasta", "jamón", "yogur", "mantequilla", "cereales",
                "garbanzo", "lenteja", "maíz", "pimiento", "zanahoria", "pepino",
                "azúcar", "sal", "harina", "chorizo", "salchichón", "lomo",
                "salmón", "merluza", "gamba", "pechuga", "muslo", "costilla",
                "manzana", "plátano", "naranja", "fresa", "uva", "melón",
                "cerveza", "vino", "agua", "zumo", "refresco", "café", "chocolate",
                "galleta", "magdalena", "croissant", "pizza", "hamburguesa",
                "fideos", "espagueti", "macarrón", "vinagre", "mermelada",
                "azafrán", "pimentón", "orégano", "albahaca",
            }
            for word in text.split():
                w = word.strip(",.")
                if w in _FOOD_VOCAB or any(w.startswith(f) for f in _FOOD_VOCAB):
                    queries.append(w)

        # Deduplicar preservando orden
        seen = set()
        unique_queries = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)

        fallback["search_queries"] = unique_queries
        return fallback
