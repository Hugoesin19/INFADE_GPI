"""
Tests para el Muro Determinista (CSP).
Verifica que el filtrado de alérgenos es absoluto.
"""

import sys
from pathlib import Path

# Asegurar que el paquete src.backend sea importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from src.backend.database import init_db, get_all_products, get_safe_products


class TestCSPFilter:
    """Tests del filtrado determinista de alérgenos."""

    def test_all_products_loaded(self):
        """La BD contiene los productos seed."""
        products = get_all_products()
        assert len(products) >= 25, f"Esperados ≥25 productos, hay {len(products)}"

    def test_filter_gluten(self):
        """Ningún producto con gluten aparece al filtrar por gluten."""
        safe = get_safe_products(["gluten"])
        for p in safe:
            assert "gluten" not in p["allergens"], \
                f"¡Fallo crítico! {p['name']} contiene gluten y pasó el filtro."

    def test_filter_lactosa(self):
        """Ningún producto con lactosa aparece al filtrar por lactosa."""
        safe = get_safe_products(["lactosa"])
        for p in safe:
            assert "lactosa" not in p["allergens"], \
                f"¡Fallo crítico! {p['name']} contiene lactosa y pasó el filtro."

    def test_filter_multiple_allergens(self):
        """Filtra múltiples alérgenos a la vez."""
        safe = get_safe_products(["gluten", "lactosa", "huevo"])
        for p in safe:
            for allergen in ["gluten", "lactosa", "huevo"]:
                assert allergen not in p["allergens"], \
                    f"{p['name']} contiene {allergen} y pasó el filtro."

    def test_no_filter_returns_all(self):
        """Sin alérgenos, devuelve todos los productos."""
        all_p = get_all_products()
        safe = get_safe_products([])
        assert len(safe) == len(all_p)

    def test_filtered_products_are_fewer(self):
        """Filtrar alérgenos reduce la cantidad de productos."""
        from unittest.mock import patch
        mock_products = [
            {"name": "Pan", "allergens": ["gluten"]},
            {"name": "Manzana", "allergens": []}
        ]
        with patch("src.backend.database.get_all_products", return_value=mock_products):
            safe = get_safe_products(["gluten"])
            assert len(safe) < len(mock_products), "El filtro de gluten debería eliminar productos."
