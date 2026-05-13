from src.backend.agents import CartState, _demo_nutritionist
import json

with open("src/backend/mercadona.db", "rb") as f:
    pass # Just to ensure we're using the live DB correctly

from src.backend.database import get_all_products
all_prods = get_all_products()

state = CartState(
    available_products=all_prods,
    selected_products=[],
    budget=50.0,
    people=3,
    diet="vegano",
    meal_type="comida",
    notes="",
    brand_preference="Hacendado",
    search_queries=["arroz bomba", "salchichon", "potito pollo"]
)
state = _demo_nutritionist(state)
for p in state.selected_products:
    print(p["name"])
