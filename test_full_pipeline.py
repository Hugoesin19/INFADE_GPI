import json
import os
import copy
from src.backend.llm_translator import translate_chat_message
from src.backend.csp_filter import apply_delta_filters
from src.backend.database import search_products_smart

print("=== TEST 1: COMPRA SEMANAL ATLETA ===")
res1 = translate_chat_message([], [], {}, "Compra semanal para un atleta con 50 euros")
print(f"Mensaje UI: {res1['mercadin_message']}")
print(f"Productos extraidos: {res1['delta']['add_queries']}")

print("\n=== TEST 2: SUSTITUCION POLLO POR CONEJO ===")
# Simular carrito con pollo
pollo_candidates = search_products_smart("pollo")
pollo = pollo_candidates[0] if pollo_candidates else None
if not pollo:
    print("No se encontro pollo en BD.")
else:
    carrito = [pollo]
    res2 = translate_chat_message([], carrito, {}, "cambia el pollo por conejo")
    print(f"Traduccion LLM - modify: {res2['delta']['modify']}")
    
    # Aplicar delta
    nuevo_carrito, _, _ = apply_delta_filters(carrito, res2['delta'], {})
    print("Carrito resultante:")
    for p in nuevo_carrito:
        print(f"- {p['name']} ({p['price']}€)")

print("\n=== TEST 3: SUSTITUCION QUE NO EXISTE (FALLBACK) ===")
carrito3 = [pollo]
res3 = translate_chat_message([], carrito3, {}, "cambia el pollo por dinosaurio")
nuevo_carrito3, _, _ = apply_delta_filters(carrito3, res3['delta'], {})
print("Carrito resultante:")
for p in nuevo_carrito3:
    print(f"- {p['name']} ({p['price']}€)")
