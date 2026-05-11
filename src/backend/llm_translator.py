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

HISTORIAL DE CONVERSACIÓN (Últimos mensajes):
{history}

INSTRUCCIONES CRÍTICAS:
1. Razona paso a paso qué necesita el usuario, considerando sus alérgenos y dieta.
2. Si el usuario pide una receta o comida, DEDUCE TODOS los ingredientes individuales necesarios para cocinarla desde cero (sal, aceite, especias, proteínas, vegetales, etc.).
3. Compara los ingredientes deducidos con el CARRITO ACTUAL.
4. Genera las "acciones_delta" para el carrito:
   - "añadir": Productos o ingredientes nuevos que el usuario pide o que has deducido y NO están ya en el carrito.
   - "eliminar": Productos que el usuario quiere quitar.
   - "modificar": Cambios explícitos (ej. cambiar pollo por conejo).

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
    {"names": {"desayuno"}, "meal_type": "desayuno",
     "ingredients": ["leche", "cereales", "pan de molde", "mermelada", "zumo de naranja"]},
    {"names": {"salmón", "salmón a la plancha"}, "meal_type": "cena",
     "ingredients": ["salmón", "brócoli", "aceite de oliva virgen", "limón", "sal"]},
    {"names": {"pollo asado", "pollo al horno"}, "meal_type": "comida",
     "ingredients": ["muslos de pollo", "patatas selección", "cebolla", "aceite de oliva virgen", "sal", "pimienta negra"]},
]


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
    Usa Gemini para entender el intent y generar la respuesta + delta.
    Reintenta automáticamente en caso de rate-limit (429).
    """
    if DEMO_MODE:
        return _fallback_chat_message(history, current_cart, profile, user_message)

    import time as _time

    max_retries = 3
    for attempt in range(max_retries):
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)

            # Formatear historial
            history_text = ""
            for msg in history[-10:]:
                role = "Usuario" if msg["role"] == "user" else "Mercadín"
                history_text += f"{role}: {msg['content']}\n"

            # Formatear carrito actual
            cart_text = "Vacío"
            if current_cart:
                cart_lines = []
                for p in current_cart:
                    cart_lines.append(f"- [ID:{p['id']}] {p['name']} ({p['brand']}) — {p['price']}€")
                cart_text = "\n".join(cart_lines)

            prompt = MERCADIN_SYSTEM_PROMPT.format(
                user_name=profile.get("name", "amigo/a"),
                people=profile.get("people", 2),
                diet=profile.get("diet", "equilibrado"),
                allergens=", ".join(profile.get("allergens", [])) or "ninguno",
                brand_preference=profile.get("brand_preference", "Hacendado"),
                budget=profile.get("per_cart_budget", 25),
                monthly_remaining=round(profile.get("monthly_budget", 200) - profile.get("month_spent", 0), 2),
                current_cart=cart_text,
                history=history_text,
            )

            full_prompt = f"{prompt}\n\nMENSAJE DEL USUARIO: {user_message}"
            response = client.models.generate_content(model=GEMINI_MODEL, contents=full_prompt)
            raw = _clean_json_response(response.text.strip())
            result = json.loads(raw)

            delta_json = result.get("acciones_delta", {})
            add_q = delta_json.get("añadir", [])
            remove_q = delta_json.get("eliminar", [])
            modify_q = delta_json.get("modificar", [])

            mapped_modify = [{"from": m.get("original", ""), "to": m.get("nuevo", "")} for m in modify_q]

            action = "no_change"
            if add_q:
                action = "add_to_cart"
            elif remove_q:
                action = "remove_from_cart"
            elif mapped_modify:
                action = "modify_cart"
                
            # Permitir que confirm venga detectado heurísticamente o por fallback (más adelante lo adaptaremos si el LLM debe confirmar)

            return {
                "mercadin_message": result.get("respuesta_chat", "Déjame procesarlo..."),
                "action": action,
                "delta": {
                    "add_queries": add_q,
                    "remove_queries": remove_q,
                    "modify": mapped_modify
                },
                "updated_constraints": {},
            }
        except Exception as e:
            error_str = str(e)
            # Retry on rate-limit (429)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                # Parse retry delay from error if available
                delay = 5 * (attempt + 1)  # 5s, 10s, 15s
                retry_match = re.search(r"retry.*?(\d+(?:\.\d+)?)s", error_str.lower())
                if retry_match:
                    delay = min(float(retry_match.group(1)) + 1, 20)
                print(f"[Mercadín] Rate-limited (429). Reintentando en {delay}s... (intento {attempt+1}/{max_retries})")
                _time.sleep(delay)
                continue
            else:
                print(f"[Mercadín] Error en chat con LLM: {e}")
                break

    # Si todos los reintentos fallan, usar fallback inteligente
    print("[Mercadín] Todos los reintentos agotados. Usando fallback inteligente.")
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

    # ─── 1. Detectar confirmación ────────────────────────
    confirm_words = {"perfecto", "listo", "confirmar", "confirmo", "añádelo", "vale", "ok", "sí", "de acuerdo", "todo bien"}
    if any(w in text for w in confirm_words) and current_cart:
        return {
            "mercadin_message": "¡Perfecto! 🎉 Tu compra está lista. ¿Confirmamos?",
            "action": "confirm",
            "delta": {"add_queries": [], "remove_queries": [], "modify": []},
            "updated_constraints": {},
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
    modify_patterns = [
        r"cambia\s+(.*?)\s+por\s+(.*)", r"sustituye\s+(.*?)\s+por\s+(.*)",
        r"pon\s+(.*?)\s+en vez de\s+(.*)", r"mejor\s+(.*?)\s+que\s+(.*)",
    ]
    for pattern in modify_patterns:
        m = re.search(pattern, text)
        if m:
            to_item = m.group(1).strip()
            from_item = m.group(2).strip()
            return {
                "mercadin_message": f"¡Hecho! Cambio {from_item} por {to_item} 🔄",
                "action": "modify_cart",
                "delta": {"add_queries": [], "remove_queries": [], "modify": [{"from": from_item, "to": to_item}]},
                "updated_constraints": {},
            }

    # ─── 4. Detectar personas ────────────────────────────
    people_match = re.search(r"para\s+(\d+)", text)
    detected_people = int(people_match.group(1)) if people_match else None

    # ─── 5. ANÁLISIS SEMÁNTICO: buscar plato + proteína ──
    ingredients = []
    dish_name = None

    # Buscar coincidencias en la base de conocimiento
    # Primero intentar match de plato completo (ej: "estofado de conejo")
    best_match_len = 0
    for keyword, ingr_list in _INGREDIENT_KNOWLEDGE.items():
        if keyword in text and len(keyword) > best_match_len:
            ingredients = list(ingr_list)
            dish_name = keyword
            best_match_len = len(keyword)

    # Buscar proteína específica mencionada
    protein_found = None
    for protein_keyword, product_name in _PROTEIN_HINTS.items():
        if protein_keyword in text:
            protein_found = product_name
            break

    # Si encontramos un plato base Y una proteína, combinar
    if dish_name and protein_found:
        # Añadir la proteína si no está ya
        has_protein = any(protein_found.lower() in i.lower() for i in ingredients)
        if not has_protein:
            ingredients.insert(0, protein_found)
        # Limpiar: quitar proteínas genéricas si hay una específica
        ingredients = [i for i in ingredients if i != protein_found or i == protein_found]

    # Si NO encontramos ningún plato pero sí proteína, crear plato genérico
    if not dish_name and protein_found:
        dish_name = protein_found
        ingredients = [protein_found, "patatas selección", "cebolla", "aceite de oliva", "sal", "pimienta negra"]

    # ─── 6. Buscar ingredientes sueltos mencionados ──────
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

    # ─── 7. Si encontramos algo, añadir al carrito ───────
    if ingredients:
        # Ajustar constraints
        updated = {}
        if detected_people:
            updated["people"] = detected_people
        if dish_name and dish_name != "ingredientes":
            updated["notes"] = dish_name
            updated["meal_type"] = "comida"

        name = dish_name or "lo que me pides"
        people_text = f" para {detected_people} personas" if detected_people else ""
        msg = (
            f"¡**{name.title()}**{people_text}! Buena elección 👨‍🍳\n\n"
            f"He preparado estos ingredientes:\n"
            + "\n".join(f"• {i.title()}" for i in ingredients[:12])
            + "\n\n¿Quieres modificar algo?"
        )

        return {
            "mercadin_message": msg,
            "action": "add_to_cart",
            "delta": {"add_queries": ingredients, "remove_queries": [], "modify": []},
            "updated_constraints": updated,
        }

    # ─── 8. Último recurso: analizar las palabras clave ──
    # Si el usuario menciona "compra", "semana", "básico", etc.
    general_keywords = {
        "compra": "compra semanal", "semana": "compra semanal", "semanal": "compra semanal",
        "básico": "compra basica", "basico": "compra basica", "básica": "compra basica",
    }
    for kw, recipe_key in general_keywords.items():
        if kw in text:
            ingr = _INGREDIENT_KNOWLEDGE.get(recipe_key, [])
            if ingr:
                return {
                    "mercadin_message": f"¡Vamos con la {recipe_key}! 🛒 He preparado los productos esenciales.",
                    "action": "add_to_cart",
                    "delta": {"add_queries": list(ingr), "remove_queries": [], "modify": []},
                    "updated_constraints": {"meal_type": "semanal", "notes": recipe_key},
                }

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
