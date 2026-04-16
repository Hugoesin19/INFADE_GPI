"""
API REST — Mercadona Autopilot.
FastAPI server que expone el pipeline completo.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import DEMO_MODE
from .database import init_db
from .llm_translator import translate_prompt
from .csp_filter import apply_filters
from .agents import run_agents
from .user_profile import get_profile, update_profile, add_spending


# ── Lifespan ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la BD al arrancar."""
    init_db()
    yield


# ── App ───────────────────────────────────────────────────

app = FastAPI(
    title="Mercadona Autopilot API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────────────

class CartRequest(BaseModel):
    prompt: str


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
    created_at: str
    updated_at: str
    monthly_remaining: float  # campo calculado


class SpendingIn(BaseModel):
    amount: float


# ── Helpers ───────────────────────────────────────────────

def _merge_profile_into_constraints(
    constraints: dict,
    explicit_fields: list[str],
    profile: dict,
) -> dict:
    """
    Fusiona el perfil del usuario como defaults en las constraints.
    Los campos que el usuario mencionó explícitamente en el prompt
    NO se sobreescriben.
    """
    # Personas: usar perfil si el prompt no lo especificó
    if "people" not in explicit_fields:
        constraints["people"] = profile["people"]

    # Alérgenos: combinar (perfil + prompt) sin duplicados
    if "allergens" not in explicit_fields:
        # Si el prompt no mencionó alérgenos, usar los del perfil
        constraints["allergens"] = list(profile.get("allergens", []))
    else:
        # Si el prompt sí mencionó, combinar ambos
        prompt_allergens = set(constraints.get("allergens", []))
        profile_allergens = set(profile.get("allergens", []))
        constraints["allergens"] = list(prompt_allergens | profile_allergens)

    # Presupuesto: usar perfil si el prompt no lo especificó
    if "budget" not in explicit_fields:
        constraints["budget"] = profile["per_cart_budget"]

    # Dieta: usar perfil si el prompt no lo especificó
    if "diet" not in explicit_fields:
        constraints["diet"] = profile["diet"]

    return constraints


# ── Endpoints: Perfil ─────────────────────────────────────

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


# ── Endpoints: Pipeline ──────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "demo_mode": DEMO_MODE}


@app.post("/api/generate-cart", response_model=CartResponse)
def generate_cart(request: CartRequest):
    """
    Pipeline completo:
      1. LLM Translator → extrae constraints
      2. Fusión con perfil de usuario → inyecta defaults
      3. CSP Filter     → filtra productos seguros
      4. Multi-Agent    → negocia cesta final
    """
    steps = []

    # ─── Paso 0: Cargar perfil del usuario ───────────────
    profile = get_profile()

    # ─── Paso 1: Traductor LLM ───────────────────────────
    t0 = time.time()
    translation = translate_prompt(request.prompt)
    constraints = translation["constraints"]
    explicit_fields = translation["explicit"]

    # Fusionar perfil como defaults inteligentes
    constraints = _merge_profile_into_constraints(
        constraints, explicit_fields, profile
    )

    steps.append({
        "id": 1,
        "text": "Analizando necesidades del cliente...",
        "status": "completed",
        "detail": f"Presupuesto: {constraints.get('budget')}€, "
                  f"Personas: {constraints.get('people')}, "
                  f"Dieta: {constraints.get('diet')}",
        "duration_ms": int((time.time() - t0) * 1000),
    })

    # ─── Paso 2: Muro Determinista (CSP) ─────────────────
    t0 = time.time()
    safe_products = apply_filters(constraints)
    allergens_blocked = constraints.get("allergens", [])
    steps.append({
        "id": 2,
        "text": "Aplicando filtros de seguridad alimentaria (CSP)...",
        "status": "completed",
        "detail": f"{len(safe_products)} productos seguros. "
                  f"Alérgenos bloqueados: {allergens_blocked or 'ninguno'}",
        "duration_ms": int((time.time() - t0) * 1000),
    })

    # ─── Paso 3: Enjambre Multi-Agente ───────────────────
    t0 = time.time()
    result = run_agents(safe_products, constraints)
    steps.append({
        "id": 3,
        "text": "Ajustes finales para mejorar la cesta...",
        "status": "completed",
        "detail": f"Cesta: {len(result.selected_products)} productos, "
                  f"Total: {result.total}€",
        "duration_ms": int((time.time() - t0) * 1000),
    })

    return CartResponse(
        products=[ProductOut(**p) for p in result.selected_products],
        total=result.total,
        budget=result.budget,
        people=result.people,
        diet=result.diet,
        meal_type=result.meal_type,
        agent_logs=result.agent_logs,
        demo_mode=DEMO_MODE,
        steps=steps,
    )
