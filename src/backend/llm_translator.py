"""
Módulo 1 — Traductor Multimodal (LLM).
Extrae variables estructuradas desde lenguaje natural usando Gemini.
Incluye funciones conversacionales para Mercadín.
"""

import json
import re
from typing import Any

from .config import GEMINI_API_KEY, GEMINI_MODEL, DEMO_MODE

# ── Prompt de sistema (original) ─────────────────────────

SYSTEM_PROMPT = """Eres un asistente de Mercadona España. Tu trabajo es extraer variables
estructuradas desde la petición del usuario para generar una cesta de la compra.

Devuelve ÚNICAMENTE un JSON válido con estos campos exactos (sin texto adicional):
{
  "budget": <número en euros, float. Si no se indica, usa 25.0>,
  "people": <número de personas, int. Si no se indica, usa 2>,
  "allergens": <lista de alérgenos a excluir. Posibles: "gluten", "lactosa", "huevo", "frutos_secos", "crustáceos", "pescado". Lista vacía si ninguno>,
  "diet": <descripción corta de la dieta/preferencia, string. Ej: "alta proteína", "vegetariano", "equilibrado". Si no se indica, usa "equilibrado">,
  "meal_type": <tipo de comida, string. Ej: "desayuno", "comida", "cena", "semanal", "general". Si no se indica, usa "general">,
  "search_queries": <lista de ingredientes ESPECÍFICOS e individuales (singulares) para preparar la receta desde cero. DESGLOSA recetas complejas al máximo. Ej para 'arroz con costra': ["arroz redondo", "huevos", "salchicha", "carne", "ave", "tomate frito"]. NUNCA uses nombres de platos compuestos como query (ej. NO uses "arroz con costra" ni "paella")>,
  "notes": <nombre de la receta o comida identificada para mostrarlo en los logs (ej: "arroz con costra")>
}

Responde SOLO con el JSON, sin markdown, sin explicaciones."""

# ── Prompt conversacional de Mercadín ────────────────────

MERCADIN_SYSTEM_PROMPT = """Eres Mercadín 🦔, el asistente de compras inteligente de Mercadona.

PERSONALIDAD:
- Cercano, eficiente, algo gracioso pero profesional. Llamas al usuario "Jefe".
- Hablas en español informal-formal.
- Usas emojis con moderación.
- Eres un Chef experto: tu objetivo es deducir el 100% de los ingredientes necesarios para cocinar cualquier receta solicitada desde cero.

CONTEXTO DEL USUARIO:
- Nombre: {user_name}
- Personas en hogar: {people}
- Dieta: {diet}
- Alérgenos: {allergens}
- Preferencia de marcas: {brand_preference}
- Presupuesto por compra: {budget}€

CARRITO ACTUAL (Productos ya añadidos):
{current_cart}

CATÁLOGO DISPONIBLE (productos reales en la base de datos):
{catalog}

HISTORIAL DE CONVERSACIÓN (Últimos mensajes):
{history}

INSTRUCCIONES CRÍTICAS:
1. Razona paso a paso qué necesita el usuario, considerando sus alérgenos y dieta.
2. Si el usuario pide una receta o comida, DEDUCE TODOS los ingredientes individuales necesarios para cocinarla desde cero.
   IMPORTANTE: Busca coincidencias en el CATÁLOGO DISPONIBLE y usa los nombres exactos de los productos que encuentres.
3. Compara los ingredientes deducidos con el CARRITO ACTUAL.
4. Genera las "acciones_delta" para el carrito:
   - "añadir": Nombres de productos del CATÁLOGO DISPONIBLE que NO están ya en el carrito.
   - "eliminar": Productos que el usuario quiere quitar.
   - "modificar": Cambios explícitos (ej. cambiar pollo por conejo).
5. En "acciones_delta.añadir", usa SOLO nombres de productos del CATÁLOGO DISPONIBLE. NO inventes productos que no existen.

FORMATO DE RESPUESTA ESTRICTO:
Debes responder ÚNICA y EXCLUSIVAMENTE con un objeto JSON válido (sin etiquetas markdown ```json). El JSON debe seguir exactamente esta estructura:

{{
  "razonamiento_interno": "Explicación breve de las restricciones, lo que pide el usuario y cómo se va a resolver.",
  "ingredientes_deducidos": ["lista exhaustiva", "de todo lo necesario", "para cocinar el plato"],
  "acciones_delta": {{
    "añadir": ["producto A", "producto B"],
    "eliminar": ["producto C"],
    "modificar": [{{"original": "producto viejo", "nuevo": "producto nuevo"}}]
  }},
  "respuesta_chat": "Texto natural, proactivo y conversacional dirigido al Jefe."
}}
"""

MERCADIN_GREETING_PROMPT = """Eres Mercadín 🦔, el asistente de compras de Mercadona.
Genera un saludo personalizado y proactivo.

CONTEXTO:
- Usuario: {user_name} (hogar de {people} personas)
- Dieta: {diet} | Alergias: {allergens}
- Preferencia de marcas: {brand_preference}
- Presupuesto restante mes: {monthly_remaining}€ | Por compra: {budget}€
- Momento: {time_greeting}, {day_context}
- Estación: {season} | Festividad: {festivity}
- Recetas de temporada: {seasonal_recipes}
- Productos de temporada: {seasonal_products}
- Productos próximos a caducar: {expiring}
- Últimas compras: {purchase_history}

INSTRUCCIONES:
1. Saluda de forma natural y personalizada
2. Haz 1-2 sugerencias concretas basadas en el contexto (temporada, hora, caducidad)
3. Sé breve (3-5 líneas máximo)
4. No preguntes datos que ya conoces (alérgenos, presupuesto)

Responde con JSON:
{{
  "greeting": "<tu saludo>",
  "suggestions": ["<sugerencia rápida 1>", "<sugerencia rápida 2>", "<sugerencia rápida 3>"]
}}"""


# ── Mapa de recetas demo ─────────────────────────────────

_RECIPE_DB = [
    {"names": {"paella", "paella valenciana", "arroz con pollo"}, "meal_type": "comida",
     "ingredients": ["arroz redondo", "muslos de pollo", "judías verdes", "tomate", "aceite de oliva virgen", "azafrán", "sal"]},
    {"names": {"arroz a banda", "arroz con marisco"}, "meal_type": "comida",
     "ingredients": ["arroz redondo", "gambas", "caldo", "tomate", "aceite de oliva virgen", "azafrán", "ajo"]},
    {"names": {"arroz con costra", "costra"}, "meal_type": "comida",
     "ingredients": ["arroz redondo", "huevos", "salchichas", "carne picada", "tomate frito", "aceite de oliva", "sal"]},
    {"names": {"spaghetti", "spaguetti", "espagueti", "espaguetis", "pasta boloñesa", "boloñesa", "bolognesa"}, "meal_type": "comida",
     "ingredients": ["espaguetis", "carne picada", "tomate frito", "cebolla", "ajo", "aceite de oliva", "sal"]},
    {"names": {"carbonara", "pasta carbonara", "espaguetis carbonara"}, "meal_type": "comida",
     "ingredients": ["espaguetis", "bacon", "huevos", "queso rallado", "pimienta negra", "aceite de oliva"]},
    {"names": {"macarrones", "macarrones con tomate"}, "meal_type": "comida",
     "ingredients": ["macarrones", "carne picada", "tomate frito", "queso rallado", "cebolla", "aceite de oliva", "sal"]},
    {"names": {"tortilla", "tortilla española", "tortilla de patatas"}, "meal_type": "comida",
     "ingredients": ["huevos", "patatas selección", "cebolla", "aceite de oliva", "sal"]},
    {"names": {"ensalada", "ensalada mixta"}, "meal_type": "comida",
     "ingredients": ["lechuga", "tomates pera", "atún", "maíz dulce", "aceite de oliva virgen", "vinagre"]},
    {"names": {"gazpacho"}, "meal_type": "comida",
     "ingredients": ["tomates pera", "pepino", "pimiento", "aceite de oliva virgen", "vinagre", "ajo", "sal"]},
    {"names": {"lentejas", "lentejas estofadas"}, "meal_type": "comida",
     "ingredients": ["lentejas", "chorizo", "patatas selección", "zanahoria", "cebolla", "aceite de oliva", "pimentón", "sal"]},
    {"names": {"hamburguesa", "hamburguesas"}, "meal_type": "comida",
     "ingredients": ["hamburguesas de vacuno", "pan de hamburguesa", "lechuga", "tomates pera", "queso tierno", "kétchup"]},
    {"names": {"pizza"}, "meal_type": "cena",
     "ingredients": ["masa de pizza", "tomate frito", "mozzarella", "jamón cocido", "aceite de oliva"]},
    {"names": {"pizza carbonara"}, "meal_type": "cena",
     "ingredients": ["masa de pizza", "tomate frito", "mozzarella", "bacon", "huevos", "queso rallado", "aceite de oliva"]},
    {"names": {"pizza barbacoa", "pizza bbq"}, "meal_type": "cena",
     "ingredients": ["masa de pizza", "tomate frito", "mozzarella", "pollo", "bacon", "cebolla", "aceite de oliva"]},
    {"names": {"pizza 4 quesos", "pizza cuatro quesos"}, "meal_type": "cena",
     "ingredients": ["masa de pizza", "tomate frito", "mozzarella", "queso rallado", "queso tierno", "aceite de oliva"]},
    {"names": {"pizza margarita", "pizza margherita"}, "meal_type": "cena",
     "ingredients": ["masa de pizza", "tomate frito", "mozzarella", "aceite de oliva"]},
    {"names": {"desayuno"}, "meal_type": "desayuno",
     "ingredients": ["leche", "cereales", "pan de molde", "mermelada", "zumo de naranja"]},
    {"names": {"salmón", "salmón a la plancha"}, "meal_type": "cena",
     "ingredients": ["salmón", "brócoli", "aceite de oliva virgen", "limón", "sal"]},
    {"names": {"pollo asado", "pollo al horno"}, "meal_type": "comida",
     "ingredients": ["muslos de pollo", "patatas selección", "cebolla", "aceite de oliva virgen", "sal", "pimienta negra"]},
]

# ── Bases y variantes para recetas compuestas ────────────
# Cuando el usuario pide "pizza carbonara", se combina la base "pizza"
# con la variante "carbonara" eliminando duplicados e ingredientes
# que no tienen sentido (ej: espaguetis no van en pizza).

_RECIPE_BASES = {
    "pizza": {
        "base_ingredients": ["masa de pizza", "tomate frito", "mozzarella", "aceite de oliva"],
        "meal_type": "cena",
        # Ingredientes de la variante que NO deben incluirse con esta base
        "exclude_from_variant": ["espaguetis", "macarrones", "pasta", "arroz", "fideos"],
    },
    "arroz": {
        "base_ingredients": ["arroz redondo", "aceite de oliva", "sal", "caldo"],
        "meal_type": "comida",
        "exclude_from_variant": ["espaguetis", "macarrones", "pasta", "masa de pizza", "fideos"],
    },
    "pasta": {
        "base_ingredients": ["espaguetis", "aceite de oliva"],
        "meal_type": "comida",
        "exclude_from_variant": ["arroz redondo", "masa de pizza"],
    },
}

_RECIPE_VARIANTS = {
    "carbonara": {
        "sauce_ingredients": ["bacon", "huevos", "queso rallado", "pimienta negra"],
    },
    "boloñesa": {
        "sauce_ingredients": ["carne picada", "tomate frito", "cebolla", "ajo", "sal"],
    },
    "bolognesa": {
        "sauce_ingredients": ["carne picada", "tomate frito", "cebolla", "ajo", "sal"],
    },
    "4 quesos": {
        "sauce_ingredients": ["mozzarella", "queso rallado", "queso tierno"],
    },
    "cuatro quesos": {
        "sauce_ingredients": ["mozzarella", "queso rallado", "queso tierno"],
    },
    "barbacoa": {
        "sauce_ingredients": ["pollo", "bacon", "cebolla", "kétchup"],
    },
    "pesto": {
        "sauce_ingredients": ["queso rallado", "piñones", "ajo", "aceite de oliva virgen"],
    },
    "al ajillo": {
        "sauce_ingredients": ["ajo", "guindilla", "aceite de oliva virgen", "sal"],
    },
    "a la marinera": {
        "sauce_ingredients": ["gambas", "mejillones", "ajo", "vino blanco", "tomate"],
    },
    "con setas": {
        "sauce_ingredients": ["champiñones", "ajo", "nata para cocinar", "sal"],
    },
    "con verduras": {
        "sauce_ingredients": ["calabacín", "pimientos", "cebolla", "zanahoria", "tomate"],
    },
}


def _try_composite_recipe(text: str) -> tuple[str | None, list[str], str]:
    """
    Intenta componer una receta a partir de base + variante.
    Ej: "pizza carbonara" -> base pizza + salsa carbonara (sin espaguetis)
    
    Returns:
        (dish_name, ingredients, meal_type) o (None, [], "")
    """
    found_base = None
    found_variant = None
    
    # Buscar base
    for base_name, base_data in _RECIPE_BASES.items():
        if base_name in text:
            found_base = (base_name, base_data)
            break
    
    # Buscar variante
    # Priorizar variantes multi-palabra
    for variant_name in sorted(_RECIPE_VARIANTS.keys(), key=len, reverse=True):
        if variant_name in text:
            found_variant = (variant_name, _RECIPE_VARIANTS[variant_name])
            break
    
    if found_base and found_variant:
        base_name, base_data = found_base
        variant_name, variant_data = found_variant
        
        # Combinar: base + salsa, excluyendo ingredientes incompatibles
        exclude_set = set(i.lower() for i in base_data.get("exclude_from_variant", []))
        
        ingredients = list(base_data["base_ingredients"])
        for ingr in variant_data["sauce_ingredients"]:
            if ingr.lower() not in exclude_set and ingr not in ingredients:
                ingredients.append(ingr)
        
        dish_name = f"{base_name} {variant_name}"
        return dish_name, ingredients, base_data["meal_type"]
    
    return None, [], ""


def _extract_ingredients_with_llm(request_text: str, profile: dict | None = None) -> dict | None:
    """
    Usa Gemini para entender CUALQUIER petición culinaria y devolver ingredientes.
    Maneja: recetas, compras semanales, dietas específicas, planificación.
    
    Returns:
        dict con {dish_name, ingredients, meal_type} o None si falla.
    """
    if DEMO_MODE:
        return None

    # Construir contexto del perfil
    profile = profile or {}
    diet = profile.get("diet", "equilibrado")
    people = profile.get("people", 2)
    allergens = profile.get("allergens", [])
    allergens_text = ", ".join(allergens) if allergens else "ninguno"

    _CHEF_PROMPT = f"""Eres un nutricionista-chef de Mercadona España. El usuario te pide algo relacionado con comida.
Devuelve SOLO un JSON con esta estructura exacta:

{{"nombre": "nombre del plato o plan", "tipo": "comida|cena|desayuno|semanal", "ingredientes": ["ingrediente1", "ingrediente2", ...]}}

Reglas:
- Ingredientes INDIVIDUALES que se encuentren en Mercadona España
- Si es una compra semanal o planificación, incluye ingredientes para varias comidas equilibradas (proteínas, carbohidratos, verduras, frutas, lácteos, básicos)
- Si menciona dieta (atleta, vegano, etc.), adapta los ingredientes a esa dieta
- Para {people} personas
- Alérgenos a EXCLUIR: {allergens_text}
- Dieta del usuario: {diet}
- Máximo 20 ingredientes para recetas, 30 para compra semanal
- Nombres simples de supermercado (ej: "pechuga de pollo", no "suprema de ave")
- Solo JSON, sin markdown, sin explicaciones

Petición del usuario: "{request_text}"
"""
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=_CHEF_PROMPT,
        )
        raw = _clean_json_response(response.text.strip())
        result = json.loads(raw)
        
        if isinstance(result, dict) and "ingredientes" in result:
            ingredients = [i.strip() for i in result["ingredientes"] if isinstance(i, str) and i.strip()]
            if ingredients:
                dish_name = result.get("nombre", request_text)
                meal_type = result.get("tipo", "comida")
                print(f"[LLM Chef] '{request_text}' → {dish_name} ({len(ingredients)} ingredientes)")
                return {"dish_name": dish_name, "ingredients": ingredients, "meal_type": meal_type}
        
        # Fallback: si devolvió una lista simple en vez de dict
        if isinstance(result, list) and len(result) > 0:
            clean = [i.strip() for i in result if isinstance(i, str) and i.strip()]
            if clean:
                return {"dish_name": request_text, "ingredients": clean, "meal_type": "comida"}
        
        return None
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            print(f"[LLM Chef] Rate-limited para '{request_text}'. Usando fallback local.")
        else:
            print(f"[LLM Chef] Error para '{request_text}': {e}")
        return None


# ══════════════════════════════════════════════════════════════
#  FUNCIONES CONVERSACIONALES (Mercadín)
# ══════════════════════════════════════════════════════════════

def generate_greeting(context: dict) -> dict:
    """
    Genera el saludo proactivo de Mercadín usando Gemini.
    Fallback determinista si no hay API key.

    Args:
        context: dict del motor de recomendaciones (recommender.py)

    Returns:
        dict con "greeting" y "suggestions"
    """
    if DEMO_MODE:
        from .recommender import build_demo_greeting
        greeting = build_demo_greeting(context)
        return {
            "greeting": greeting,
            "suggestions": context.get("quick_replies", []),
        }

    import time as _time

    uc = context["user_context"]
    tc = context["time_context"]
    sc = context["season_context"]

    prompt = MERCADIN_GREETING_PROMPT.format(
        user_name=uc["name"] or "amigo/a",
        people=uc["people"],
        diet=uc["diet"],
        allergens=", ".join(uc["allergens"]) or "ninguno",
        brand_preference=uc.get("brand_preference", "Hacendado"),
        monthly_remaining=uc["monthly_remaining"],
        budget=uc["per_cart_budget"],
        time_greeting=tc["greeting"],
        day_context=tc["day"],
        season=sc["season"],
        festivity=sc.get("festivity") or "ninguna",
        seasonal_recipes=", ".join(sc["recipes"]),
        seasonal_products=", ".join(sc["products"]),
        expiring=json.dumps(context.get("expiring_products", []), ensure_ascii=False),
        purchase_history=json.dumps(context.get("purchase_history", []), ensure_ascii=False),
    )

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        raw = _clean_json_response(response.text.strip())
        result = json.loads(raw)

        return {
            "greeting": result.get("greeting", "¡Hola! 🦔 ¿En qué te puedo ayudar?"),
            "suggestions": result.get("suggestions", context.get("quick_replies", [])),
        }
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            print("[Mercadín] Saludo rate-limited (429). Pasando a fallback inmediato para no bloquear UI.")
        else:
            print(f"[Mercadín] Error generando saludo con LLM: {e}")
        
        # Fallback determinista inmediato
        from .recommender import build_demo_greeting
        return {
            "greeting": build_demo_greeting(context),
            "suggestions": context.get("quick_replies", []),
        }


def translate_chat_message(
    history: list[dict],
    current_cart: list[dict],
    profile: dict,
    user_message: str,
) -> dict:
    """
    Procesa un mensaje del usuario en el contexto conversacional.
    Usa SIEMPRE el motor determinista para respuesta instantánea.
    El LLM se reserva para el saludo proactivo (donde la latencia es aceptable).
    """
    return _fallback_chat_message(history, current_cart, profile, user_message)


# ══════════════════════════════════════════════════════════════
#  FALLBACK INTELIGENTE (sin LLM)
# ══════════════════════════════════════════════════════════════

# Base de conocimiento de ingredientes por tipo de plato
_INGREDIENT_KNOWLEDGE = {
    # Proteínas
    "conejo": ["conejo", "cebolla", "zanahoria", "tomate", "aceite de oliva", "ajo", "sal", "pimienta negra", "vino blanco"],
    "estofado": ["patatas selección", "cebolla", "zanahoria", "tomate", "aceite de oliva", "ajo", "sal", "pimienta negra", "caldo"],
    "guiso": ["patatas selección", "cebolla", "zanahoria", "tomate", "aceite de oliva", "ajo", "sal", "caldo"],
    "pollo": ["muslos de pollo", "aceite de oliva", "sal", "pimienta negra"],
    "ternera": ["carne picada", "aceite de oliva", "sal", "pimienta negra"],
    "cerdo": ["lomo de cerdo", "aceite de oliva", "sal", "pimienta negra"],
    "salmon": ["salmón", "aceite de oliva", "limón", "sal"],
    "salmón": ["salmón", "aceite de oliva", "limón", "sal"],
    "merluza": ["merluza", "aceite de oliva", "limón", "sal"],
    "gambas": ["gambas", "aceite de oliva", "ajo", "sal"],
    "atun": ["atún", "aceite de oliva"],
    "atún": ["atún", "aceite de oliva"],
    "bacalao": ["bacalao", "aceite de oliva", "ajo", "pimientos"],

    # Platos
    "paella": ["arroz redondo", "muslos de pollo", "judías verdes", "tomate", "aceite de oliva virgen", "azafrán", "sal", "caldo"],
    "tortilla": ["huevos", "patatas selección", "cebolla", "aceite de oliva", "sal"],
    "gazpacho": ["tomates pera", "pepino", "pimiento", "aceite de oliva virgen", "vinagre", "ajo", "sal"],
    "ensalada": ["lechuga", "tomates pera", "maíz dulce", "atún", "aceite de oliva virgen", "vinagre"],
    "cocido": ["garbanzos", "carne picada", "patatas selección", "zanahoria", "caldo", "chorizo", "sal"],
    "lentejas": ["lentejas", "chorizo", "patatas selección", "zanahoria", "cebolla", "aceite de oliva", "pimentón", "sal"],
    "fabada": ["alubias blancas", "chorizo", "cebolla", "ajo", "aceite de oliva", "pimentón", "sal"],
    "macarrones": ["macarrones", "carne picada", "tomate frito", "queso rallado", "cebolla", "aceite de oliva", "sal"],
    "espaguetis": ["espaguetis", "carne picada", "tomate frito", "cebolla", "ajo", "aceite de oliva", "sal"],
    "carbonara": ["espaguetis", "bacon", "huevos", "queso rallado", "pimienta negra", "aceite de oliva"],
    "hamburguesa": ["hamburguesas de vacuno", "pan de hamburguesa", "lechuga", "tomates pera", "queso tierno", "kétchup"],
    "pizza": ["masa de pizza", "tomate frito", "mozzarella", "jamón cocido", "aceite de oliva"],
    "lasaña": ["pasta penne", "carne picada", "tomate frito", "queso rallado", "nata para cocinar", "cebolla"],
    "croquetas": ["croquetas de jamón"],
    "pisto": ["calabacín", "pimientos rojos", "pimientos verdes", "tomates pera", "cebolla", "aceite de oliva", "sal"],
    "revuelto": ["huevos", "champiñones", "aceite de oliva", "sal"],
    "arroz": ["arroz redondo", "aceite de oliva", "sal", "caldo"],
    "sopa": ["caldo", "fideos", "zanahoria", "cebolla", "sal"],
    "crema": ["calabacín", "patatas selección", "cebolla", "caldo", "nata para cocinar", "sal"],
    "risotto": ["arroz redondo", "champiñones", "queso rallado", "cebolla", "caldo", "mantequilla", "aceite de oliva"],
    "curry": ["pechuga de pollo", "cebolla", "tomate", "aceite de oliva", "arroz redondo", "sal"],
    "fajitas": ["pechuga de pollo", "pimientos rojos", "pimientos verdes", "cebolla", "aceite de oliva", "sal"],
    "wok": ["pechuga de pollo", "pimientos", "cebolla", "zanahoria", "aceite de oliva", "sal"],
    "empanada": ["empanadillas de atún"],
    "desayuno": ["leche", "cereales de avena", "pan de molde", "mermelada de fresa", "zumo de naranja"],
    "merienda": ["pan de molde", "chocolate con leche", "zumo de naranja"],
    "cena ligera": ["lechuga", "tomates pera", "atún", "aceite de oliva virgen"],
    "compra semanal": ["leche", "pan de molde", "huevos", "arroz redondo", "pasta", "tomate frito", "aceite de oliva", "pollo", "lechuga", "tomates pera", "patatas selección", "cebolla", "fruta"],
    "compra basica": ["leche", "pan de molde", "huevos", "arroz redondo", "aceite de oliva", "tomate frito", "sal"],
    "barbacoa": ["costillas de cerdo", "hamburguesas de vacuno", "pan de hamburguesa", "pimientos", "cebolla", "aceite de oliva", "kétchup", "cerveza"],
}

# Comidas que implican proteína específica
_PROTEIN_HINTS = {
    "conejo": "conejo", "pollo": "muslos de pollo", "cerdo": "lomo de cerdo",
    "ternera": "filetes de ternera", "cordero": "cordero", "pavo": "pavo",
    "salmón": "salmón", "salmon": "salmón", "merluza": "merluza",
    "bacalao": "bacalao", "gambas": "gambas", "langostinos": "langostinos",
    "atún": "atún", "atun": "atún", "sardinas": "sardinas",
}


def _fallback_chat_message(
    history: list[dict],
    current_cart: list[dict],
    profile: dict,
    user_message: str,
) -> dict:
    """
    Fallback INTELIGENTE cuando no hay LLM disponible.
    Analiza el texto para deducir ingredientes de CUALQUIER plato,
    incluso si no está en la receta DB hardcodeada.
    """
    text = user_message.lower().strip()

    # ─── 1. Detectar confirmación (solo si el mensaje es puramente confirmatorio) ──
    confirm_words = {"perfecto", "listo", "confirmar", "confirmo", "añádelo", "vale", "ok", "sí", "de acuerdo", "todo bien"}
    negate_words = {"pero", "aunque", "también", "añade", "quita", "pon", "cambia", "más", "menos", "otro", "quiero"}
    text_words = set(text.split())
    is_pure_confirm = (
        len(text_words) <= 4
        and any(w in text for w in confirm_words)
        and not any(w in text for w in negate_words)
    )
    if is_pure_confirm and current_cart:
        return {
            "mercadin_message": "¡Perfecto! 🎉 Tu compra está lista. ¿Confirmamos?",
            "action": "confirm",
            "delta": {"add_queries": [], "remove_queries": [], "modify": []},
            "updated_constraints": {},
        }

    # ─── 1b. Detectar declaración de ALERGIA ─────────────
    allergen_map = {
        "gluten": "gluten", "trigo": "gluten", "celiac": "gluten", "celiaco": "gluten", "celíaco": "gluten",
        "lactosa": "lactosa", "leche": "lactosa", "lácteo": "lactosa", "lacteo": "lactosa",
        "huevo": "huevo", "huevos": "huevo",
        "frutos secos": "frutos_secos", "nueces": "frutos_secos", "cacahuete": "frutos_secos", "almendra": "frutos_secos",
        "marisco": "crustáceos", "crustáceo": "crustáceos", "gamba": "crustáceos",
        "pescado": "pescado",
    }
    allergen_triggers = [
        r"(?:soy |tengo )(?:alergi[cao]|intoleranci[ao]|intolerant[ea])\s+(?:al?|a la|a los|a las)\s+([\w\s]+)",
        r"(?:alergi[cao]|intoleranci[ao])\s+(?:al?|a la|a los|a las)\s+([\w\s]+)",
        r"no puedo (?:comer|tomar|consumir)\s+([\w\s]+)",
    ]
    detected_allergens = []

    # Primero: detectar con patrones conversacionales
    for pattern in allergen_triggers:
        m = re.search(pattern, text)
        if m:
            raw = m.group(1).strip().rstrip(".")
            for keyword, allergen in allergen_map.items():
                if keyword in raw:
                    if allergen not in detected_allergens:
                        detected_allergens.append(allergen)

    # Segundo: detectar "sin X" como declaración de alergia (no como eliminación de carrito)
    # Solo si parece una declaración general (no "sin cebolla" que es eliminación)
    if not detected_allergens:
        sin_match = re.findall(r"(?:^|[\s,])sin\s+([\w\s]+?)(?:[,.\s]|$)", text)
        for raw in sin_match:
            raw = raw.strip()
            for keyword, allergen in allergen_map.items():
                if keyword in raw:
                    if allergen not in detected_allergens:
                        detected_allergens.append(allergen)

    if detected_allergens:
        # Construir lista de productos a eliminar del carrito actual
        from .csp_filter import _product_has_allergen
        remove_queries = []
        for p in current_cart:
            for allergen in detected_allergens:
                if _product_has_allergen(p, allergen):
                    remove_queries.append(p["name"])
                    break

        allergen_names = ", ".join(detected_allergens)
        removed_text = ""
        if remove_queries:
            removed_text = f"\n\n🚫 He quitado del carrito: {', '.join(remove_queries[:5])}"
            if len(remove_queries) > 5:
                removed_text += f" y {len(remove_queries) - 5} más"

        msg = (
            f"¡Anotado, Jefe! 🦔 Registro tu alergia a **{allergen_names}**. "
            f"A partir de ahora filtro todos los productos con estos alérgenos."
            f"{removed_text}"
            f"\n\n¿Necesitas algo más?"
        )

        action = "remove_from_cart" if remove_queries else "no_change"
        return {
            "mercadin_message": msg,
            "action": action,
            "delta": {
                "add_queries": [],
                "remove_queries": remove_queries,
                "modify": [],
            },
            "updated_constraints": {"allergens": detected_allergens},
        }

    # ─── 2. Detectar eliminación ─────────────────────────
    remove_patterns = [r"quita\s+(.*)", r"elimina\s+(.*)", r"sin\s+(.*)", r"no quiero\s+(.*)"]
    for pattern in remove_patterns:
        m = re.search(pattern, text)
        if m:
            item = m.group(1).strip()
            return {
                "mercadin_message": f"Entendido, quito {item} del carrito 🦔",
                "action": "remove_from_cart",
                "delta": {"add_queries": [], "remove_queries": [item], "modify": []},
                "updated_constraints": {},
            }

    # ─── 3. Detectar sustitución ─────────────────────────
    # Patrones: (grupo1=lo que se quita, grupo2=lo que se pone)
    modify_patterns = [
        (r"cambia\s+(.*?)\s+por\s+(.*)", 1, 2),       # cambia pollo por conejo
        (r"sustituye\s+(.*?)\s+por\s+(.*)", 1, 2),     # sustituye pollo por conejo
        (r"pon(?:me)?\s+(.*?)\s+en vez de\s+(.*)", 2, 1),  # pon conejo en vez de pollo → from=pollo, to=conejo
        (r"en vez de\s+(.*?)\s+pon(?:me)?\s+(.*)", 1, 2),  # en vez de pollo pon conejo
        (r"mejor\s+(.*?)\s+que\s+(.*)", 2, 1),         # mejor conejo que pollo → from=pollo, to=conejo
        (r"prefiero\s+(.*?)\s+(?:a|al|que)\s+(.*)", 2, 1), # prefiero conejo a pollo
        (r"quiero\s+(.*?)\s+en lugar de\s+(.*)", 2, 1),    # quiero conejo en lugar de pollo
    ]

    def _clean_item(s: str) -> str:
        """Limpia artículos y preposiciones del nombre extraído."""
        s = s.strip().rstrip(".,;:!?")
        s = re.sub(r"^(?:el|la|los|las|un|una|unos|unas|del|al)\s+", "", s)
        return s.strip()

    for pattern, from_idx, to_idx in modify_patterns:
        m = re.search(pattern, text)
        if m:
            from_item = _clean_item(m.group(from_idx))
            to_item = _clean_item(m.group(to_idx))
            return {
                "mercadin_message": f"¡Hecho! Cambio {from_item} por {to_item} 🔄",
                "action": "modify_cart",
                "delta": {"add_queries": [], "remove_queries": [], "modify": [{"from": from_item, "to": to_item}]},
                "updated_constraints": {},
            }

    # ─── 4. Detectar personas ────────────────────────────
    people_match = re.search(r"para\s+(\d+)", text)
    detected_people = int(people_match.group(1)) if people_match else None

    # ─── 5. RESOLUCIÓN DE RECETAS / PLANIFICACIÓN ────────
    # Prioridad: DB exacta → composición → IA → keywords → vocabulario suelto
    ingredients = []
    dish_name = None
    meal_type_hint = None

    # ── 5a. Buscar en _RECIPE_DB (matches exactos, instantáneo) ──
    best_recipe = None
    best_recipe_score = 0
    for recipe in _RECIPE_DB:
        for name in recipe["names"]:
            if name in text:
                score = len(name)
                if " " in name:
                    score += 100  # Priorizar matches multi-palabra
                if score > best_recipe_score:
                    best_recipe = recipe
                    best_recipe_score = score

    if best_recipe:
        ingredients = list(best_recipe["ingredients"])
        meal_type_hint = best_recipe.get("meal_type")
        for name in sorted(best_recipe["names"], key=len, reverse=True):
            if name in text:
                dish_name = name
                break
        if not dish_name:
            dish_name = list(best_recipe["names"])[0]

    # ── 5b. Composición inteligente (pizza + carbonara, instantáneo) ──
    if not ingredients:
        comp_name, comp_ingredients, comp_meal = _try_composite_recipe(text)
        if comp_name and comp_ingredients:
            ingredients = comp_ingredients
            dish_name = comp_name
            meal_type_hint = comp_meal

    # ── 5c. Proteína específica (combinar con plato base) ──
    protein_found = None
    for protein_keyword, product_name in _PROTEIN_HINTS.items():
        if protein_keyword in text:
            protein_found = product_name
            break

    if dish_name and protein_found:
        has_protein = any(protein_found.lower() in i.lower() for i in ingredients)
        if not has_protein:
            ingredients.insert(0, protein_found)

    if not dish_name and protein_found and not ingredients:
        dish_name = protein_found
        ingredients = [protein_found, "patatas selección", "cebolla", "aceite de oliva", "sal"]

    # ── 5d. IA COMO FUENTE PRIMARIA (para todo lo no reconocido) ──
    if not ingredients:
        # Limpiar el texto para extraer la petición culinaria
        dish_text = text
        for strip_pattern in [
            r"(?:quiero|necesito|ponme|hazme|prepara|dame)\s+(?:hacer\s+)?(?:una?\s+)?",
            r"\s*(?:para\s+\d+\s+personas?)",
            r"\s*(?:con\s+\d+\s+euros?)",
            r"\s*(?:por\s+favor)",
        ]:
            dish_text = re.sub(strip_pattern, "", dish_text).strip()

        if len(dish_text) >= 3:
            llm_result = _extract_ingredients_with_llm(dish_text, profile)
            if llm_result:
                ingredients = llm_result["ingredients"]
                dish_name = llm_result["dish_name"]
                meal_type_hint = llm_result.get("meal_type", "comida")

    # ── 5e. Fallback local: _INGREDIENT_KNOWLEDGE ──
    if not ingredients:
        best_match_score = 0
        for keyword, ingr_list in _INGREDIENT_KNOWLEDGE.items():
            if keyword in text:
                score = len(keyword)
                if " " in keyword:
                    score += 50
                if score > best_match_score:
                    ingredients = list(ingr_list)
                    dish_name = keyword
                    best_match_score = score

    # ── 5f. Ingredientes sueltos mencionados ──
    if not ingredients:
        _FOOD_VOCAB = {
            "arroz", "pollo", "carne", "pescado", "verdura", "fruta", "leche",
            "huevo", "huevos", "pan", "queso", "tomate", "lechuga", "patata",
            "patatas", "cebolla", "atún", "aceite", "pasta", "jamón", "yogur",
            "cereales", "salmón", "salmon", "merluza", "gambas", "pechuga",
            "manzana", "plátano", "naranja", "cerveza", "agua", "zumo", "café",
            "chocolate", "galletas", "chorizo", "bacon", "champiñones", "espinacas",
            "brócoli", "zanahoria", "zanahorias", "calabacín", "pimiento", "pimientos",
            "ajo", "pepino", "lentejas", "garbanzos", "alubias", "fideos",
        }
        found_foods = []
        for word in text.split():
            clean_w = word.strip(".,;:!?¿¡")
            if clean_w in _FOOD_VOCAB:
                found_foods.append(clean_w)
        if found_foods:
            ingredients = found_foods
            dish_name = "ingredientes"

    # ─── 6. Si encontramos algo, añadir al carrito ───────
    if ingredients:
        updated = {}
        if detected_people:
            updated["people"] = detected_people
        if dish_name and dish_name != "ingredientes":
            updated["notes"] = dish_name
            updated["meal_type"] = meal_type_hint or "comida"

        name = dish_name or "lo que me pides"
        people_text = f" para {detected_people} personas" if detected_people else ""
        msg = (
            f"¡**{name.title()}**{people_text}! Buena elección 👨‍🍳\n\n"
            f"He preparado estos ingredientes:\n"
            + "\n".join(f"• {i.title()}" for i in ingredients[:20])
            + "\n\n¿Quieres modificar algo?"
        )

        return {
            "mercadin_message": msg,
            "action": "add_to_cart",
            "delta": {"add_queries": ingredients, "remove_queries": [], "modify": []},
            "updated_constraints": updated,
        }

    # ─── 7. Último recurso: no se reconoció nada ─────────

    # Conversación general - pero con contexto útil
    return {
        "mercadin_message": (
            "Entendido 🦔 No he reconocido un plato concreto. "
            "Prueba a decirme algo como:\n\n"
            "• \"Quiero hacer una paella para 4\"\n"
            "• \"Ponme un estofado de conejo\"\n"
            "• \"Compra básica de la semana\"\n"
            "• \"Necesito pollo, arroz y verdura\"\n\n"
            "¡O dime los ingredientes que necesitas!"
        ),
        "action": "no_change",
        "delta": {"add_queries": [], "remove_queries": [], "modify": []},
        "updated_constraints": {},
    }


# ══════════════════════════════════════════════════════════════
#  HELPER: Catálogo para prompt del LLM
# ══════════════════════════════════════════════════════════════

# Vocabulario de alimentos para extraer keywords del mensaje del usuario
_FOOD_KEYWORDS_SET = {
    "arroz", "pollo", "carne", "pescado", "verdura", "fruta", "leche",
    "huevo", "huevos", "pan", "queso", "tomate", "lechuga", "patata",
    "patatas", "cebolla", "atún", "aceite", "pasta", "jamón", "yogur",
    "cereales", "salmón", "salmon", "merluza", "gambas", "pechuga",
    "manzana", "plátano", "naranja", "cerveza", "agua", "zumo", "café",
    "chocolate", "galletas", "chorizo", "bacon", "champiñones", "espinacas",
    "brócoli", "zanahoria", "zanahorias", "calabacín", "pimiento", "pimientos",
    "ajo", "pepino", "lentejas", "garbanzos", "alubias", "fideos",
    "sal", "azúcar", "vinagre", "macarrones", "espaguetis", "mantequilla",
    "nata", "harina", "pimienta", "orégano", "azafrán", "pimentón",
    "conejo", "ternera", "cerdo", "cordero", "pavo", "salmón",
    "bacalao", "sardinas", "langostinos", "costillas", "hamburguesa",
    "pizza", "tortilla", "paella", "gazpacho", "ensalada", "lentejas",
    "macarrones", "espaguetis", "carbonara", "lasaña", "risotto",
}


def _build_catalog_for_prompt(user_message: str, excluded_allergens: list[str] = None) -> str:
    """
    Pre-busca productos relevantes en la BD basándose en el mensaje del usuario.
    Devuelve un texto formateado con los productos disponibles para incluir en el prompt del LLM.
    """
    from .database import search_products_smart, get_safe_products

    text = user_message.lower().strip()
    keywords = []

    # 1. Extraer keywords de comida del mensaje
    for word in text.split():
        clean = word.strip(".,;:!?¿¡\"'")
        if clean in _FOOD_KEYWORDS_SET:
            keywords.append(clean)

    # 2. Buscar platos conocidos y extraer sus ingredientes como keywords
    for recipe in _RECIPE_DB:
        for name in recipe["names"]:
            if name in text:
                for ingr in recipe["ingredients"]:
                    # Usar la primera palabra significativa del ingrediente
                    first_word = ingr.split()[0].lower()
                    if first_word not in keywords and len(first_word) >= 3:
                        keywords.append(ingr)
                break

    # 3. Buscar en _INGREDIENT_KNOWLEDGE
    for keyword, ingr_list in _INGREDIENT_KNOWLEDGE.items():
        if keyword in text:
            for ingr in ingr_list:
                if ingr not in keywords:
                    keywords.append(ingr)
            break

    if not keywords:
        return "No se han encontrado productos relevantes. El usuario puede estar haciendo una consulta general."

    # 4. Buscar productos en la BD para cada keyword
    seen_ids = set()
    catalog_lines = []
    for kw in keywords[:15]:  # Máx 15 keywords para no saturar el prompt
        results = search_products_smart(kw, limit=3)
        for p in results:
            if p["id"] not in seen_ids:
                # Filtrar alérgenos si aplica
                if excluded_allergens:
                    product_allergens = set(p.get("allergens", []))
                    if product_allergens.intersection(excluded_allergens):
                        continue
                seen_ids.add(p["id"])
                catalog_lines.append(
                    f"- {p['name']} ({p['brand']}) — {p['price']}€ | {p.get('subcategory', '')}"
                )

    if not catalog_lines:
        return "No se encontraron productos que coincidan con la búsqueda."

    return "\n".join(catalog_lines[:50])  # Máx 50 productos en el catálogo


# ══════════════════════════════════════════════════════════════
#  FUNCIÓN ORIGINAL (retrocompatibilidad)
# ══════════════════════════════════════════════════════════════

def translate_prompt(user_text: str) -> dict[str, Any]:
    """Original: traduce texto libre a constraints. Se mantiene para /api/generate-cart."""
    print(f"DEBUG PROMPT: {user_text!r}")
    if DEMO_MODE:
        return {"constraints": _fallback_translate(user_text), "explicit": [], "used_fallback": True}

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=f"{SYSTEM_PROMPT}\n\n--- Petición del usuario ---\n{user_text}",
        )
        raw = _clean_json_response(response.text.strip())
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            return _fallback_translate(user_text)
        explicit = _detect_explicit_fields(user_text, result)
        return {"constraints": result, "explicit": explicit, "used_fallback": False}
    except Exception as e:
        print(f"[LLM] Error genérico: {e}")
        return {"constraints": _fallback_translate(user_text), "explicit": [], "used_fallback": True}


# ── Helpers ───────────────────────────────────────────────

def _clean_json_response(raw: str) -> str:
    """Limpia posibles bloques markdown de la respuesta."""
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])
    return raw


def _detect_explicit_fields(user_text: str, constraints: dict) -> list[str]:
    text = user_text.lower()
    explicit = []
    if re.search(r"\d+\s*(?:euros|€|eur)", text):
        explicit.append("budget")
    if re.search(r"(?:persona|comensales|gente|para\s+\d+)", text):
        explicit.append("people")
    if re.search(r"(?:sin |no |libre de |alergi)", text):
        explicit.append("allergens")
    if re.search(r"(?:prote[ií]n|vegan|vegetarian|light|bajo en grasa|dieta)", text):
        explicit.append("diet")
    return explicit


def _fallback_translate(user_text: str) -> dict[str, Any]:
    """Traductor determinista sin LLM (retrocompatibilidad)."""
    text = user_text.lower().strip()
    result = {"budget": 25.0, "people": 2, "allergens": [], "diet": "equilibrado",
              "meal_type": "general", "search_queries": [], "notes": user_text}
    explicit = []

    budget_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:euros|€|eur)", text)
    if budget_match:
        result["budget"] = float(budget_match.group(1).replace(",", "."))
        explicit.append("budget")

    for pattern in [r"para\s+(\d+)\s*persona", r"(\d+)\s*persona", r"para\s+(\d+)"]:
        m = re.search(pattern, text)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 20:
                result["people"] = n
                explicit.append("people")
                break

    allergen_map = {"gluten": "gluten", "lactosa": "lactosa", "huevo": "huevo",
                    "frutos secos": "frutos_secos", "marisco": "crustáceos", "pescado": "pescado"}
    for keyword, allergen in allergen_map.items():
        if f"sin {keyword}" in text or f"no {keyword}" in text:
            if allergen not in result["allergens"]:
                result["allergens"].append(allergen)
    if result["allergens"]:
        explicit.append("allergens")

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
        for name in matched_recipe["names"]:
            if name in text:
                result["notes"] = name
                break
    else:
        _FOOD_VOCAB = {"arroz", "pollo", "carne", "pescado", "leche", "huevo", "huevos", "pan",
                       "queso", "tomate", "lechuga", "patata", "cebolla", "atún", "aceite", "pasta",
                       "jamón", "yogur", "cereales", "salmón", "merluza", "gambas", "manzana", "plátano"}
        result["search_queries"] = [w.strip(".,;:!?¿¡") for w in text.split() if w.strip(".,;:!?¿¡") in _FOOD_VOCAB]

    return {"constraints": result, "explicit": explicit}
