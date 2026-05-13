import json
from src.backend.llm_translator import translate_chat_message
from src.backend.agents import run_agents_delta
from src.backend.database import get_all_products

res = translate_chat_message([], [], {}, "muffins de chocolate healthy con platano")
delta = res['delta']
print(f"Delta: {delta}")

safe_products = get_all_products()
state = run_agents_delta([], delta, safe_products, {})
print("Carrito tras agentes:")
for p in state.selected_products:
    print(p["name"])
