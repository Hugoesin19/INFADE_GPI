"""
Script diseñado para enriquecer la base de datos de Mercadona con información nutricional y alérgenos.
Dada la falta de macros en la API pública de Mercadona, usa un proceso en dos fases:
1. Hit a `tienda.mercadona.es/api/products/{id}/` para extraer el EAN (código de barras) y los alérgenos en HTML.
2. Hit a `world.openfoodfacts.org/api/v2/product/{ean}.json` para extraer kcal, protein, carbs y fat.

Usa concurrencia para procesar miles de peticiones ràpidamente.
"""

import sqlite3
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

from .config import DB_PATH

MERCADONA_API = "https://tienda.mercadona.es/api/products/{}/"
OFF_API = "https://world.openfoodfacts.org/api/v2/product/{}.json"

HEADERS_MERCADONA = {"User-Agent": "MercadonaAutopilot/1.0"}
HEADERS_OFF = {"User-Agent": "MercadonaAutopilot/1.0 - Python Script"}


def clean_html(raw_html: str) -> list[str]:
    """Limpia el string HTML de alérgenos de Mercadona y devuelve lista."""
    if not raw_html:
        return []
    # Ej: "Contiene <strong>trigo y productos derivados</strong>. Contiene <strong>huevos</strong>."
    clean = re.sub(r'<[^>]+>', '', raw_html)
    clean = clean.replace("Contiene ", "").replace(".", "")
    items = [x.strip().lower() for x in clean.split(" y ") if x.strip()]
    return list(set(items))


def enrich_product(row) -> dict:
    product_id = row["id"]
    mercadona_id = row["mercadona_id"]
    name = row["name"]
    
    update_data = {
        "id": product_id,
        "allergens": "[]",
        "kcal_100g": 0.0,
        "protein_100g": 0.0,
        "carbs_100g": 0.0,
        "fat_100g": 0.0,
        "success": False
    }

    try:
        # 1. Fetch EAN from Mercadona
        resp_m = requests.get(MERCADONA_API.format(mercadona_id), headers=HEADERS_MERCADONA, timeout=10)
        if resp_m.status_code != 200:
            return update_data

        data_m = resp_m.json()
        ean = data_m.get("ean")
        
        # Parse Allergens directly from Mercadona
        nutrition = data_m.get("nutrition_information", {})
        if nutrition and isinstance(nutrition, dict):
            raw_allergens = nutrition.get("allergens", "")
            if raw_allergens:
                import json
                cleaned = clean_html(raw_allergens)
                update_data["allergens"] = json.dumps(cleaned, ensure_ascii=False)

        if not ean:
            update_data["success"] = True # We got allergens at least
            return update_data

        # 2. Fetch Macros from OpenFoodFacts using EAN
        resp_o = requests.get(OFF_API.format(ean), headers=HEADERS_OFF, timeout=10)
        if resp_o.status_code == 200:
            data_o = resp_o.json()
            if data_o.get("status") == 1:
                nutriments = data_o.get("product", {}).get("nutriments", {})
                
                update_data["kcal_100g"] = float(nutriments.get("energy-kcal_100g", 0))
                update_data["protein_100g"] = float(nutriments.get("proteins_100g", 0))
                update_data["carbs_100g"] = float(nutriments.get("carbohydrates_100g", 0))
                update_data["fat_100g"] = float(nutriments.get("fat_100g", 0))
                update_data["success"] = True

    except Exception as e:
        print(f"Error {name}: {e}")

    return update_data


def main():
    print("=" * 60)
    print("  ENRIQUECIENDO PRODUCTOS (Mercadona API + OpenFoodFacts)")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, mercadona_id, name FROM products").fetchall()
    
    total = len(rows)
    print(f"📦 Procesando {total} productos en total...\n")

    updates = []
    completed = 0
    success = 0

    # Usamos 10 threads para no saturar ninguna de las dos APIs de golpe, pero ir suficientemente rápido
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(enrich_product, row): row for row in rows}
        
        for future in as_completed(futures):
            completed += 1
            res = future.result()
            updates.append((
                res["allergens"], res["kcal_100g"], res["protein_100g"],
                res["carbs_100g"], res["fat_100g"], res["id"]
            ))
            if res["success"]:
                success += 1
                
            if completed % 100 == 0:
                print(f"⏳ Progreso: {completed}/{total} procesados... ({success} macros/alérgenos rescatados)")

    print(f"\n💾 Guardando {len(updates)} actualizaciones en la base de datos...")
    
    # Guardar en bulk
    conn.executemany("""
        UPDATE products 
        SET allergens = ?, kcal_100g = ?, protein_100g = ?, carbs_100g = ?, fat_100g = ?
        WHERE id = ?
    """, updates)
    conn.commit()
    conn.close()

    print(f"🎉 Éxito. {success} productos tienen ahora macros y alérgenos reales instalados.")

if __name__ == "__main__":
    main()
