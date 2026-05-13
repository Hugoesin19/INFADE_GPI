"""
API REST — Mercadona Autopilot / Mercadín 🦔
FastAPI server que expone el pipeline completo + endpoints conversacionales.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import DEMO_MODE
from .database import init_db, get_expiring_products
from .llm_translator import translate_prompt, generate_greeting, translate_chat_message
from .csp_filter import apply_filters, apply_delta_filters, validate_cart_allergens
from .agents import run_agents, run_agents_delta
from .user_profile import get_profile, update_profile, add_spending
from .recommender import generate_greeting_context
from .chat_session import (
    create_session, get_session, add_message,
    update_cart_state, update_constraints, confirm_session,
    get_purchase_history,
)


# ── Lifespan ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la BD al arrancar."""
    init_db()
    yield


# ── App ───────────────────────────────────────────────────

app = FastAPI(
    title="Mercadona Autopilot API — Mercadín 🦔",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════
#  SCHEMAS
# ══════════════════════════════════════════════════════════════

class ProductOut(BaseModel):
    id: int
    name: str
    brand: str
    category: str
    subcategory: str
    price: float
    unit_size: float
    size_format: str
    packaging: str
    allergens: list[str]
    kcal_100g: float
    protein_100g: float
    carbs_100g: float
    fat_100g: float
    image_url: str
    days_to_expiry: int


# ── Chat schemas ─────────────────────────────────────────

class ChatStartResponse(BaseModel):
    session_id: str
    greeting: str
    suggestions: list[str]
    profile_summary: dict
    demo_mode: bool


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str


class CartDelta(BaseModel):
    added: list[ProductOut]
    removed: list[int]
    modified: list[ProductOut]


class ChatMessageResponse(BaseModel):
    session_id: str
    mercadin_message: str
    cart_delta: Optional[CartDelta] = None
    current_cart: list[ProductOut]
    total: float
    budget: float
    confirmed: bool
    agent_logs: list[str]
    demo_mode: bool


class ChatConfirmRequest(BaseModel):
    session_id: str


class ChatConfirmResponse(BaseModel):
    session_id: str
    final_cart: list[ProductOut]
    total: float
    message: str


# ── Legacy schemas ───────────────────────────────────────

class CartRequest(BaseModel):
    prompt: str


class CartResponse(BaseModel):
    products: list[ProductOut]
    total: float
    budget: float
    people: int
    diet: str
    meal_type: str
    agent_logs: list[str]
    demo_mode: bool
    steps: list[dict]


class ProfileIn(BaseModel):
    name: Optional[str] = None
    people: Optional[int] = None
    allergens: Optional[list[str]] = None
    diet: Optional[str] = None
    monthly_budget: Optional[float] = None
    per_cart_budget: Optional[float] = None
    preferences: Optional[str] = None
    brand_preference: Optional[str] = None


class ProfileOut(BaseModel):
    id: int
    name: str
    people: int
    allergens: list[str]
    diet: str
    monthly_budget: float
    per_cart_budget: float
    month_spent: float
    month_start: str
    preferences: str
    brand_preference: str
    created_at: str
    updated_at: str
    monthly_remaining: float


class SpendingIn(BaseModel):
    amount: float


# ══════════════════════════════════════════════════════════════
#  CHAT ENDPOINTS — Mercadín 🦔
# ══════════════════════════════════════════════════════════════

@app.post("/api/chat/start", response_model=ChatStartResponse)
def chat_start():
    """
    Inicia una nueva sesión de chat con Mercadín.
    Carga perfil, genera saludo proactivo y devuelve session_id.
    """
    profile = get_profile()
    session = create_session(user_id=profile["id"])

    # Generar contexto para el saludo proactivo
    expiring = get_expiring_products(limit=5)
    history = get_purchase_history(user_id=profile["id"], limit=5)
    context = generate_greeting_context(profile, expiring, history)

    # Generar saludo con LLM o fallback
    greeting_data = generate_greeting(context)
    greeting_text = greeting_data["greeting"]
    suggestions = greeting_data["suggestions"]

    # Guardar saludo en historial de la sesión
    add_message(session["id"], "assistant", greeting_text)

    # Guardar constraints iniciales del perfil
    initial_constraints = {
        "budget": profile.get("per_cart_budget", 25),
        "people": profile.get("people", 2),
        "diet": profile.get("diet", "equilibrado"),
        "allergens": profile.get("allergens", []),
        "brand_preference": profile.get("brand_preference", "Hacendado"),
        "meal_type": "general",
        "notes": "",
    }
    update_constraints(session["id"], initial_constraints)

    return ChatStartResponse(
        session_id=session["id"],
        greeting=greeting_text,
        suggestions=suggestions,
        profile_summary={
            "name": profile.get("name", ""),
            "people": profile.get("people", 2),
            "allergens": profile.get("allergens", []),
            "diet": profile.get("diet", "equilibrado"),
            "per_cart_budget": profile.get("per_cart_budget", 25),
            "brand_preference": profile.get("brand_preference", "Hacendado"),
            "monthly_remaining": round(
                profile.get("monthly_budget", 200) - profile.get("month_spent", 0), 2
            ),
        },
        demo_mode=DEMO_MODE,
    )


@app.post("/api/chat/message", response_model=ChatMessageResponse)
def chat_message(request: ChatMessageRequest):
    """
    Procesa un mensaje del usuario y devuelve la respuesta de Mercadín
    junto con los cambios al carrito (delta).
    """
    session = get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    if session["status"] == "confirmed":
        raise HTTPException(status_code=400, detail="Esta sesión ya fue confirmada")

    profile = get_profile()
    current_cart = session["cart_state"]
    constraints = session["constraints"]

    # Guardar mensaje del usuario
    add_message(request.session_id, "user", request.message)

    # Procesar con LLM
    llm_result = translate_chat_message(
        history=session["messages"],
        current_cart=current_cart,
        profile=profile,
        user_message=request.message,
    )

    mercadin_msg = llm_result["mercadin_message"]
    action = llm_result["action"]
    delta = llm_result["delta"]
    updated_constraints = llm_result.get("updated_constraints", {})

    # Actualizar constraints si el translator devolvió cambios
    if updated_constraints:
        for key, value in updated_constraints.items():
            if value is not None:
                if key == "allergens":
                    # Merge: unir alérgenos nuevos con los existentes
                    existing = set(constraints.get("allergens", []))
                    existing.update(value)
                    constraints["allergens"] = list(existing)
                else:
                    constraints[key] = value
        update_constraints(request.session_id, constraints)

    # Procesar el delta sobre el carrito
    cart_delta_out = None
    agent_logs = []
    confirmed = False

    if action == "confirm":
        confirmed = True
    elif action in ("add_to_cart", "modify_cart", "remove_from_cart", "clear_cart"):
        if action == "clear_cart":
            current_cart = []
            cart_delta_out = CartDelta(added=[], removed=[p["id"] for p in session["cart_state"]], modified=[])
        else:
            # Obtener TODOS los productos seguros
            safe_products = apply_filters(constraints)
            
            # Ejecutar agentes para calcular el nuevo estado del carrito
            agent_result = run_agents_delta(
                current_cart=current_cart,
                delta=delta,
                available_products=safe_products,
                constraints=constraints,
            )
            new_cart = agent_result.selected_products
            agent_logs = agent_result.agent_logs

            # Validación POST-agente: muro de alérgenos ABSOLUTO
            allergens = constraints.get("allergens", [])
            if allergens:
                new_cart, csp_logs = validate_cart_allergens(
                    new_cart, allergens, safe_products
                )
                agent_logs.extend(csp_logs)
            
            # Determinar added, removed_ids para el cliente (frontend)
            old_ids = {p["id"] for p in current_cart}
            new_ids = {p["id"] for p in new_cart}
            
            added = [p for p in new_cart if p["id"] not in old_ids]
            removed_ids = list(old_ids - new_ids)

            current_cart = new_cart
            cart_delta_out = CartDelta(
                added=[ProductOut(**p) for p in added],
                removed=removed_ids,
                modified=[],
            )

        # Persistir estado del carrito
        update_cart_state(request.session_id, current_cart)

    # Guardar respuesta de Mercadín
    add_message(request.session_id, "assistant", mercadin_msg)

    total = round(sum(p.get("price", 0) for p in current_cart), 2)
    budget = constraints.get("budget", 25)

    return ChatMessageResponse(
        session_id=request.session_id,
        mercadin_message=mercadin_msg,
        cart_delta=cart_delta_out,
        current_cart=[ProductOut(**p) for p in current_cart],
        total=total,
        budget=budget,
        confirmed=confirmed,
        agent_logs=agent_logs,
        demo_mode=DEMO_MODE,
    )


@app.post("/api/chat/confirm", response_model=ChatConfirmResponse)
def chat_confirm(request: ChatConfirmRequest):
    """Confirma la compra y guarda en historial."""
    session = confirm_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")

    cart = session["cart_state"]
    total = round(sum(p.get("price", 0) for p in cart), 2)

    # Registrar gasto mensual
    add_spending(total)

    return ChatConfirmResponse(
        session_id=request.session_id,
        final_cart=[ProductOut(**p) for p in cart],
        total=total,
        message=f"¡Compra confirmada! 🎉 Total: {total}€. Guardado en tu historial.",
    )


@app.get("/api/chat/{session_id}")
def chat_get_session(session_id: str):
    """Recupera una sesión existente (para reconexión)."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    return session


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def _merge_profile_into_constraints(constraints, explicit_fields, profile):
    if "people" not in explicit_fields:
        constraints["people"] = profile["people"]
    if "allergens" not in explicit_fields:
        constraints["allergens"] = list(profile.get("allergens", []))
    else:
        prompt_allergens = set(constraints.get("allergens", []))
        profile_allergens = set(profile.get("allergens", []))
        constraints["allergens"] = list(prompt_allergens | profile_allergens)
    if "budget" not in explicit_fields:
        constraints["budget"] = profile["per_cart_budget"]
    if "diet" not in explicit_fields:
        constraints["diet"] = profile["diet"]
    return constraints


# ══════════════════════════════════════════════════════════════
#  LEGACY ENDPOINTS (retrocompatibilidad)
# ══════════════════════════════════════════════════════════════

@app.get("/api/profile", response_model=ProfileOut)
def get_user_profile():
    """Devuelve el perfil del usuario (crea uno por defecto si no existe)."""
    profile = get_profile()
    profile["monthly_remaining"] = round(
        profile["monthly_budget"] - profile["month_spent"], 2
    )
    return ProfileOut(**profile)


@app.put("/api/profile", response_model=ProfileOut)
def update_user_profile(data: ProfileIn):
    """Actualiza el perfil del usuario con los campos proporcionados."""
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    profile = update_profile(update_data)
    profile["monthly_remaining"] = round(
        profile["monthly_budget"] - profile["month_spent"], 2
    )
    return ProfileOut(**profile)


@app.post("/api/profile/spending", response_model=ProfileOut)
def register_spending(data: SpendingIn):
    """Registra un gasto en el presupuesto mensual."""
    profile = add_spending(data.amount)
    profile["monthly_remaining"] = round(
        profile["monthly_budget"] - profile["month_spent"], 2
    )
    return ProfileOut(**profile)


@app.get("/api/health")
def health():
    return {"status": "ok", "demo_mode": DEMO_MODE}


@app.post("/api/generate-cart", response_model=CartResponse)
def generate_cart(request: CartRequest):
    """Pipeline completo legacy (retrocompatibilidad)."""
    steps = []
    profile = get_profile()

    t0 = time.time()
    translation = translate_prompt(request.prompt)
    constraints = translation["constraints"]
    explicit_fields = translation["explicit"]
    used_fallback = translation.get("used_fallback", False)

    constraints = _merge_profile_into_constraints(constraints, explicit_fields, profile)

    steps.append({
        "id": 1, "text": "Analizando necesidades del cliente...", "status": "completed",
        "detail": f"Presupuesto: {constraints.get('budget')}€, Personas: {constraints.get('people')}, Dieta: {constraints.get('diet')}",
        "duration_ms": int((time.time() - t0) * 1000),
    })

    t0 = time.time()
    safe_products = apply_filters(constraints)
    steps.append({
        "id": 2, "text": "Aplicando filtros de seguridad alimentaria (CSP)...", "status": "completed",
        "detail": f"{len(safe_products)} productos seguros. Alérgenos bloqueados: {constraints.get('allergens', []) or 'ninguno'}",
        "duration_ms": int((time.time() - t0) * 1000),
    })

    t0 = time.time()
    result = run_agents(safe_products, constraints)

    # Validación POST-agente: muro de alérgenos ABSOLUTO
    allergens = constraints.get("allergens", [])
    if allergens:
        result.selected_products, csp_logs = validate_cart_allergens(
            result.selected_products, allergens, safe_products
        )
        result.total = round(sum(p["price"] for p in result.selected_products), 2)
        result.agent_logs.extend(csp_logs)

    steps.append({
        "id": 3, "text": "Ajustes finales para mejorar la cesta...", "status": "completed",
        "detail": f"Cesta: {len(result.selected_products)} productos, Total: {result.total}€",
        "duration_ms": int((time.time() - t0) * 1000),
    })

    return CartResponse(
        products=[ProductOut(**p) for p in result.selected_products],
        total=result.total, budget=result.budget, people=result.people,
        diet=result.diet, meal_type=result.meal_type, agent_logs=result.agent_logs,
        demo_mode=used_fallback, steps=steps,
    )


# ══════════════════════════════════════════════════════════════
#  STATIC FILES — Serve frontend UI
# ══════════════════════════════════════════════════════════════

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"


@app.get("/")
def serve_index():
    return FileResponse(_UI_DIR / "index.html")


# Mount static assets (CSS, images, etc.)
app.mount("/assets", StaticFiles(directory=str(_UI_DIR / "assets")), name="assets")
app.mount("/", StaticFiles(directory=str(_UI_DIR)), name="static")

