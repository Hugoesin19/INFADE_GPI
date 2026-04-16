"""
Test de integración del pipeline completo en modo demo.
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))


class TestPipeline:
    """Test del pipeline completo LLM→CSP→Agentes en modo demo."""

    @classmethod
    def setup_class(cls):
        os.environ.pop("GEMINI_API_KEY", None)  # Forzar modo demo
        
        from src.backend import config
        config.DEMO_MODE = True

    def test_full_pipeline_returns_cart(self):
        """El pipeline completo devuelve una cesta con productos."""
        from src.backend.llm_translator import translate_prompt
        from src.backend.csp_filter import apply_filters
        from src.backend.agents import run_agents

        # Paso 1: Traducir
        translation = translate_prompt("Paella para 4 personas, 15€")
        constraints = translation["constraints"]
        assert "budget" in constraints
        assert "allergens" in constraints

        # Paso 2: Filtrar
        safe = apply_filters(constraints)
        assert len(safe) > 0, "El CSP debería devolver productos."

        # Paso 3: Agentes
        result = run_agents(safe, constraints)
        assert len(result.selected_products) > 0, "Los agentes deberían seleccionar productos."
        assert result.total > 0, "El total debería ser > 0."
        assert result.total <= constraints["budget"], \
            f"Total {result.total}€ supera presupuesto {constraints['budget']}€"

    def test_pipeline_with_allergens(self):
        """El pipeline respeta alérgenos incluso tras pasar por agentes."""
        from src.backend.csp_filter import apply_filters
        from src.backend.agents import run_agents

        constraints = {
            "budget": 20.0,
            "people": 2,
            "allergens": ["gluten", "lactosa"],
            "diet": "equilibrado",
            "meal_type": "cena",
            "notes": "",
        }

        safe = apply_filters(constraints)
        result = run_agents(safe, constraints)

        for p in result.selected_products:
            for allergen in ["gluten", "lactosa"]:
                assert allergen not in p["allergens"], \
                    f"¡Seguridad comprometida! {p['name']} contiene {allergen}."

    def test_pipeline_budget_respected(self):
        """El total de la cesta no supera el presupuesto."""
        from src.backend.csp_filter import apply_filters
        from src.backend.agents import run_agents

        constraints = {
            "budget": 8.0,
            "people": 1,
            "allergens": [],
            "diet": "equilibrado",
            "meal_type": "general",
            "notes": "",
        }

        safe = apply_filters(constraints)
        result = run_agents(safe, constraints)
        assert result.total <= 8.0, f"Total {result.total}€ excede presupuesto 8€."
