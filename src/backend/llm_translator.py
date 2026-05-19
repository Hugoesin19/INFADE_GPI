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


def _generate_basic_recipe(dish_name: str, ingredients: list[str]) -> str:
    """
    Genera instrucciones de receta paso a paso básicas para platos conocidos.
    Se usa como fallback cuando el LLM no está disponible, para que el frontend
    pueda mostrar la foto de la receta.
    """
    # Recetas específicas con pasos reales
    _BASIC_RECIPES = {
        "paella": "1. Calienta aceite en la paellera y sofríe el pollo.\n2. Añade las judías verdes y sofríe 2 min.\n3. Agrega el tomate rallado y cocina 3 min.\n4. Vierte agua caliente (el doble que de arroz) y el azafrán.\n5. Cuando hierva, añade el arroz repartiéndolo bien.\n6. Cocina 18-20 min a fuego medio-alto sin remover.\n7. Deja reposar 5 min antes de servir.",
        "tortilla": "1. Pela y corta las patatas en láminas finas.\n2. Fríe las patatas en abundante aceite a fuego medio.\n3. Bate los huevos con sal en un bol grande.\n4. Escurre las patatas y mézclalas con el huevo batido.\n5. Vierte en la sartén y cocina 4 min por cada lado.\n6. Dale la vuelta con un plato y cuaja el otro lado.",
        "carbonara": "1. Cuece los espaguetis en agua con sal según el paquete.\n2. Corta el bacon en tiras y fríe hasta que esté crujiente.\n3. Bate los huevos con el queso rallado y pimienta.\n4. Escurre la pasta y mézclala con el bacon (fuego apagado).\n5. Añade la mezcla de huevo y remueve rápido.\n6. Sirve inmediatamente con más queso por encima.",
        "espaguetis": "1. Cuece los espaguetis en abundante agua con sal.\n2. Sofríe la cebolla y el ajo picados en aceite.\n3. Añade la carne picada y cocina hasta que se dore.\n4. Agrega el tomate frito y cocina 10 min a fuego lento.\n5. Escurre la pasta y mézclala con la salsa.\n6. Sirve con queso rallado por encima.",
        "macarrones": "1. Cuece los macarrones según las instrucciones del paquete.\n2. Sofríe la cebolla picada en aceite de oliva.\n3. Añade la carne picada y dórala bien.\n4. Incorpora el tomate frito y cocina 8 min.\n5. Mezcla con los macarrones escurridos.\n6. Gratina con queso rallado en el horno 5 min.",
        "gazpacho": "1. Lava y trocea los tomates, pepino, pimiento y ajo.\n2. Tritúralo todo con una batidora hasta obtener una crema fina.\n3. Añade aceite de oliva, vinagre y sal al gusto.\n4. Pasa por un colador si quieres textura más fina.\n5. Refrigera al menos 2 horas antes de servir.",
        "ensalada": "1. Lava y trocea la lechuga.\n2. Corta los tomates en gajos.\n3. Escurre el atún y el maíz.\n4. Monta todo en un bol o plato.\n5. Aliña con aceite de oliva y vinagre al gusto.",
        "lentejas": "1. Sofríe la cebolla y la zanahoria en aceite.\n2. Añade el pimentón, remueve y agrega las lentejas.\n3. Cubre con agua, añade las patatas troceadas y el chorizo.\n4. Cocina a fuego lento 35-40 min.\n5. Rectifica de sal y sirve caliente.",
        "hamburguesa": "1. Saca las hamburguesas del frigorífico 15 min antes.\n2. Cocínalas en sartén o plancha 4 min por cada lado.\n3. Tuesta los panes ligeramente.\n4. Monta: pan, lechuga, hamburguesa, queso, tomate, pan.\n5. Sirve con kétchup al gusto.",
        "pizza": "1. Estira la masa de pizza sobre la bandeja del horno.\n2. Extiende el tomate frito como base.\n3. Reparte la mozzarella y el resto de ingredientes.\n4. Hornea a 220°C durante 12-15 min.\n5. Saca, corta en porciones y sirve caliente.",
        "salmón": "1. Seca el salmón con papel de cocina y salpimienta.\n2. Calienta aceite en una sartén a fuego medio-alto.\n3. Cocina el salmón 4 min por cada lado.\n4. Exprime limón por encima al servir.\n5. Acompaña con el brócoli cocido al vapor.",
        "pollo": "1. Salpimienta los muslos de pollo generosamente.\n2. Séllalos en una sartén con aceite bien caliente.\n3. Añade las patatas y cebolla troceadas.\n4. Hornea todo a 200°C durante 40 min.\n5. Sirve cuando el pollo esté dorado y crujiente.",
        "desayuno": "1. Calienta la leche y sirve con los cereales.\n2. Tuesta el pan de molde y úntalo con mermelada.\n3. Sirve el zumo de naranja bien frío.\n4. ¡Listo para empezar el día con energía!",
    }

    # Buscar receta específica
    dish_lower = dish_name.lower()
    for key, recipe in _BASIC_RECIPES.items():
        if key in dish_lower:
            return recipe

    # Receta genérica si no hay match específico
    ingr_text = ", ".join(ingredients[:6])
    return (
        f"1. Prepara todos los ingredientes: {ingr_text}.\n"
        f"2. Calienta aceite en una sartén o cacerola.\n"
        f"3. Cocina los ingredientes principales a fuego medio.\n"
        f"4. Sazona al gusto con sal y especias.\n"
        f"5. Sirve caliente y ¡disfruta!"
    )


def _extract_ingredients_with_llm(request_text: str, profile: dict | None = None, ai_mode: str = "gemini") -> dict | None:
    """
    Usa Gemini para entender CUALQUIER petición culinaria y devolver ingredientes.
    Maneja: recetas, compras semanales, dietas específicas, planificación.
    
    Returns:
        dict con {dish_name, ingredients, meal_type} o None si falla.
    """
    if ai_mode == "demo":
        return None

    # Construir contexto del perfil
    profile = profile or {}
    diet = profile.get("diet", "equilibrado")
    people = profile.get("people", 2)
    allergens = profile.get("allergens", [])
    allergens_text = ", ".join(allergens) if allergens else "ninguno"

    try:
        from .database import get_all_products
        catalog_names = [p["name"] for p in get_all_products()]
        catalog_str = ", ".join(catalog_names)
    except Exception as e:
        catalog_str = "catálogo no disponible, usa ingredientes comunes"

    _CHEF_PROMPT = f"""Eres un nutricionista-chef de Mercadona España. El usuario te pide algo relacionado con comida.
Devuelve SOLO un JSON con esta estructura exacta:

{{"nombre": "nombre del plato o plan", "tipo": "comida|cena|desayuno|merienda|semanal", "ingredientes": ["ingrediente1", "ingrediente2", ...], "receta": "Instrucciones paso a paso para elaborar el plato en casa", "planificacion": null}}

Si el usuario pide una COMPRA SEMANAL o PLANIFICACIÓN, usa esta estructura:
{{"nombre": "Plan semanal", "tipo": "semanal", "ingredientes": ["todos los ingredientes necesarios"], "receta": null, "planificacion": [{{"dia": "Lunes", "comida": "Nombre del plato", "cena": "Nombre del plato"}}, ...]}}

Reglas:
- IMPORTANTE: Usa ÚNICA Y EXCLUSIVAMENTE nombres exactos que aparezcan en este CATÁLOGO: [{catalog_str}]
- Para recetas: incluye TODOS los ingredientes necesarios sin excepción. No añadas ingredientes que no sean necesarios para el plato.
- Para compra semanal: haz un planning de lunes a domingo con comida y cena, e incluye todos los ingredientes que se necesitarían.
- Si menciona dieta (atleta, vegano, etc.), adapta los ingredientes a esa dieta
- Para {people} personas
- Alérgenos a EXCLUIR: {allergens_text}
- Dieta del usuario: {diet}
- Máximo 20 ingredientes para recetas, 30 para compra semanal
- En "receta" escribe instrucciones claras, paso a paso, con tiempos de cocción
- Solo JSON, sin markdown, sin explicaciones

Petición del usuario: "{request_text}"
"""
    try:
        if ai_mode == "groq":
            import requests
            from .config import GROQ_API_KEY
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": _CHEF_PROMPT},
                    {"role": "user", "content": request_text}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2
            }
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data)
            res.raise_for_status()
            response_text = res.json()["choices"][0]["message"]["content"]
            raw = _clean_json_response(response_text.strip())
            result = json.loads(raw)
        else: # gemini
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
                recipe_text = result.get("receta", None)
                planning = result.get("planificacion", None)
                print(f"[LLM Chef] '{request_text}' → {dish_name} ({len(ingredients)} ingredientes)")
                return {
                    "dish_name": dish_name,
                    "ingredients": ingredients,
                    "meal_type": meal_type,
                    "recipe": recipe_text,
                    "planning": planning,
                }
        
        # Fallback: si devolvió una lista simple en vez de dict
        if isinstance(result, list) and len(result) > 0:
            clean = [i.strip() for i in result if isinstance(i, str) and i.strip()]
            if clean:
                return {"dish_name": request_text, "ingredients": clean, "meal_type": "comida", "recipe": None, "planning": None}
        
        return None
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            print(f"[LLM Chef] Rate-limited para '{request_text}'. Usando fallback local.")
        else:
            print(f"[LLM Chef] Error para '{request_text}': {e}")
        
        # Auto-fallback: si Gemini falla, intentar con Groq
        if ai_mode == "gemini":
            print(f"[LLM Chef] Auto-fallback a Groq para '{request_text}'...")
            try:
                return _extract_ingredients_with_llm(request_text, profile, "groq")
            except Exception as e2:
                print(f"[LLM Chef] Groq fallback también falló: {e2}")
        
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
    ai_mode: str = "gemini",
) -> dict:
    """
    Procesa un mensaje del usuario en el contexto conversacional.
    Usa SIEMPRE el motor determinista para respuesta instantánea.
    El LLM se reserva para el saludo proactivo (donde la latencia es aceptable).
    """
    return _fallback_chat_message(history, current_cart, profile, user_message, ai_mode)


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
    
    # Conceptos abstractos / intenciones
    "dulce saludable": ["yogur proteínas hacendado", "chocolate negro 72% hacendado", "fresas", "almendras tostadas hacendado"],
    "algo dulce": ["chocolate con leche hacendado", "galletas de chocolate hacendado", "flan de huevo hacendado"],
    "dulce": ["chocolate negro 72% hacendado", "fresas", "yogur natural hacendado"],
    "saludable": ["manzanas golden", "brócoli", "salmón", "arroz integral hacendado", "yogur natural hacendado"],
    "merendar": ["pan de molde integral hacendado", "pavo en lonchas hacendado", "zumo de naranja", "yogur natural hacendado", "plátanos de canarias"],
    "merienda": ["pan de molde integral hacendado", "pavo en lonchas hacendado", "zumo de naranja", "yogur natural hacendado", "plátanos de canarias"],
    "postre": ["flan de huevo hacendado", "natillas de vainilla hacendado", "yogur de fresa hacendado", "fresas"],
    "sano": ["pechuga de pollo fileteada", "arroz integral hacendado", "brócoli", "manzanas golden", "almendras tostadas hacendado"],
    "fitness": ["pechuga de pollo fileteada", "arroz integral hacendado", "brócoli", "yogur proteínas hacendado", "atún claro en aceite de oliva hacendado"],
    "vegano": ["tofu", "garbanzos hacendado", "bebida de avena hacendado", "lentejas pardinas hacendado", "espinacas frescas hacendado"],
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
    ai_mode: str = "gemini",
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

    # ─── 2a. Detectar VACIAR CARRITO / ELIMINAR TODO ──────
    clear_patterns = [
        r"vac[ií]a(?:r)?\s+(?:el\s+)?carrito",
        r"elimina(?:r)?\s+todo",
        r"quita(?:r)?\s+todo",
        r"borra(?:r)?\s+(?:el\s+)?carrito",
        r"limpia(?:r)?\s+(?:el\s+)?carrito",
        r"quiero\s+empezar\s+de\s+(?:cero|nuevo)",
        r"resetea(?:r)?\s+(?:el\s+)?carrito",
    ]
    for pattern in clear_patterns:
        if re.search(pattern, text):
            return {
                "mercadin_message": "¡Hecho! 🧹 He vaciado el carrito por completo. ¿En qué puedo ayudarte ahora?",
                "action": "clear_cart",
                "delta": {"add_queries": [], "remove_queries": [], "modify": []},
                "updated_constraints": {},
            }

    # ─── 2b. Detectar eliminación de producto concreto ───
    remove_patterns = [
        r"quita(?:r)?\s+(.*)",
        r"elimina(?:r)?\s+(.*)",
        r"no quiero\s+(.*)",
        r"quiero quitar\s+(.*)",
    ]
    for pattern in remove_patterns:
        m = re.search(pattern, text)
        if m:
            item = m.group(1).strip()
            # Limpiar artículos del item
            item = re.sub(r'^(el|la|los|las|un|una)\s+', '', item)
            if item:
                return {
                    "mercadin_message": f"Entendido, quito **{item}** del carrito 🦔",
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
    # Prioridad absoluta: LLM Chef → DB exacta → composición → keywords → vocabulario
    ingredients = []
    dish_name = None
    meal_type_hint = None
    llm_result = None

    # ── 5a. IA COMO FUENTE PRIMARIA ──
    # Enviar el texto COMPLETO al LLM — tiene todo el contexto del catálogo
    if ai_mode != "demo" and len(text) >= 3:
        llm_result = _extract_ingredients_with_llm(text, profile, ai_mode)
        if llm_result:
            ingredients = llm_result["ingredients"]
            dish_name = llm_result["dish_name"]
            meal_type_hint = llm_result.get("meal_type", "comida")

    # Limpiar el texto para los fallbacks locales
    dish_text = text
    for strip_pattern in [
        r"(?:quiero|necesito|ponme|hazme|prepara|dame)\s+(?:hacer\s+)?(?:una?\s+)?",
        r"\s*(?:para\s+\d+\s+personas?)",
        r"\s*(?:con\s+\d+\s+euros?)",
        r"\s*(?:por\s+favor)",
    ]:
        dish_text = re.sub(strip_pattern, "", dish_text).strip()

    # ── 5b. Buscar en _RECIPE_DB (fallback local, matches exactos) ──
    if not ingredients:
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

    # ── 5c. Composición inteligente (pizza + carbonara, fallback) ──
    if not ingredients:
        comp_name, comp_ingredients, comp_meal = _try_composite_recipe(text)
        if comp_name and comp_ingredients:
            ingredients = comp_ingredients
            dish_name = comp_name
            meal_type_hint = comp_meal

    # ── 5d. Proteína específica (combinar con plato base) ──
    if not ingredients:
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

    # ── 5e. Fallback local: _INGREDIENT_KNOWLEDGE ──
    if not ingredients:
        text_for_search = re.sub(r'\s+', ' ', text.replace("pero", " ").replace("y", " ").replace("para", " ")).strip()
        best_match_score = 0
        for keyword, ingr_list in _INGREDIENT_KNOWLEDGE.items():
            if keyword in text_for_search:
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
            "ajo", "pepino", "lentejas", "garbanzos", "alubias", "fideos", "tofu", "avena",
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
        
        # Build recipe/planning sections if the LLM provided them
        recipe_text = ""
        planning_text = ""
        recipe_data = None
        
        if llm_result is not None:
            if llm_result.get("recipe"):
                recipe_data = {
                    "nombre": llm_result["dish_name"],
                    "receta": llm_result["recipe"],
                    "ingredientes": [i.title() for i in ingredients],
                    "personas": detected_people or profile.get("people", 2),
                }
                recipe_text = f"\n\n📋 **Receta:**\n{llm_result['recipe']}"
            
            if llm_result.get("planning"):
                planning_lines = []
                for day in llm_result["planning"]:
                    if isinstance(day, dict):
                        dia = day.get("dia", "")
                        comida = day.get("comida", "—")
                        cena = day.get("cena", "—")
                        planning_lines.append(f"  **{dia}**: 🍽️ {comida} | 🌙 {cena}")
                if planning_lines:
                    planning_text = "\n\n📅 **Plan semanal:**\n" + "\n".join(planning_lines)
                    recipe_data = {
                        "nombre": llm_result["dish_name"],
                        "planificacion": llm_result["planning"],
                        "ingredientes": [i.title() for i in ingredients],
                        "personas": detected_people or profile.get("people", 2),
                    }

        # Si no hay recipe_data del LLM, generar uno básico con receta auto-generada
        if recipe_data is None and dish_name and dish_name != "ingredientes":
            # Generar instrucciones básicas para que el frontend muestre la foto
            auto_recipe = _generate_basic_recipe(dish_name, ingredients)
            recipe_data = {
                "nombre": name.title(),
                "receta": auto_recipe,
                "ingredientes": [i.title() for i in ingredients],
                "personas": detected_people or profile.get("people", 2),
            }
            recipe_text = f"\n\n📋 **Receta:**\n{auto_recipe}"

        msg = (
            f"¡**{name.title()}**{people_text}! Buena elección 👨‍🍳\n\n"
            f"He preparado estos ingredientes:\n"
            + "\n".join(f"• {i.title()}" for i in ingredients[:30])
            + recipe_text
            + planning_text
            + "\n\n¿Quieres modificar algo?"
        )

        result = {
            "mercadin_message": msg,
            "action": "add_to_cart",
            "delta": {"add_queries": ingredients, "remove_queries": [], "modify": []},
            "updated_constraints": updated,
        }
        if recipe_data:
            result["recipe_data"] = recipe_data
        return result

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
