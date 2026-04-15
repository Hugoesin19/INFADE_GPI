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
        
        # Extracción naive de keywords para que al menos busque algo coherente
        words = [w.strip(",.") for w in user_text.lower().split() if len(w) > 3]
        
        # Intentar extraer presupuesto del texto naively
        import re
        budget_match = re.search(r"(\d+)\s*(euros|€)", user_text)
        if budget_match:
            fallback["budget"] = float(budget_match.group(1))
            
        fallback["search_queries"] = words
        return fallback
