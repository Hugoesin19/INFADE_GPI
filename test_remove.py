import json
from src.backend.llm_translator import translate_chat_message
from src.backend.agents import run_agents_delta

# Create a fake initial state matching the paella output
carrito = [
    {"id": 1, "name": "Arroz bomba Hacendado", "price": 1.0, "category": "Arroz", "brand": "Hacendado"},
    {"id": 2, "name": "Alcachofas congeladas Hacendado", "price": 1.5, "category": "Verdura", "brand": "Hacendado"}
]

res = translate_chat_message([], carrito, {}, "quita las alcachofas")
delta = res['delta']
print(f"Delta: {delta}")

from src.backend.csp_filter import apply_filters
safe_products = carrito # Fake available
state = run_agents_delta(carrito, delta, safe_products, {})
print("Carrito tras eliminar:")
for p in state.selected_products:
    print(p["name"])
