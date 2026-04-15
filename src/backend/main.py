"""
API REST — Mercadona Autopilot.
FastAPI server que expone el pipeline completo.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import DEMO_MODE
from .database import init_db
from .llm_translator import translate_prompt
from .csp_filter import apply_filters
from .agents import run_agents


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


# ── Endpoints ─────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "demo_mode": DEMO_MODE}


@app.post("/api/generate-cart", response_model=CartResponse)
def generate_cart(request: CartRequest):
    """
    Pipeline completo:
      1. LLM Translator → extrae constraints
      2. CSP Filter     → filtra productos seguros
      3. Multi-Agent    → negocia cesta final
    """
    steps = []

    # ─── Paso 1: Traductor LLM ───────────────────────────
    t0 = time.time()
    constraints = translate_prompt(request.prompt)
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
