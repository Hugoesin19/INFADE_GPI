"""
Scraper de productos de Mercadona.
Usa la API pública de tienda.mercadona.es para obtener todos los productos
de alimentación y poblar la base de datos SQLite.

Uso:
    python3 -m src.backend.scraper
"""

import json
import sqlite3
import time
import requests

from .config import DB_PATH

API_BASE = "https://tienda.mercadona.es/api"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "MercadonaAutopilot/1.0"})

# IDs de las categorías raíz que son de ALIMENTACIÓN
FOOD_TOP_IDS = {
    12, 18, 15, 13, 9, 24, 19, 8, 3, 7, 4, 17, 14, 1, 6, 2, 5, 16, 11, 10,
}


def _fetch_json(url: str) -> dict | list | None:
    """Fetch JSON con reintentos, sin raise_for_status para manejar 404."""
    for attempt in range(3):
        try:
            resp = SESSION.get(url, timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == 2:
                print(f"  ⚠ Fallido para {url}: {e}")
            time.sleep(1)
    return None


def _extract_brand(display_name: str) -> str:
    """Extrae la marca del nombre del producto."""
    known = [
        "Hacendado", "Deliplus", "Bosque Verde", "Compy", "Quely",
        "Casa Juncal", "Polasal",
    ]
    for brand in known:
        if brand.lower() in display_name.lower():
            return brand
    parts = display_name.rsplit(" ", 1)
    return parts[-1] if len(parts) > 1 else "Otro"


def scrape_all_products() -> list[dict]:
    """
    Scrapea todos los productos de alimentación.
    
    Estructura de la API:
      /api/categories/           → lista de categorías raíz con subcategorías (IDs)
      /api/categories/{subid}/   → subcategoría con sub-subcategorías y productos
    """
    print("🔍 Descargando catálogo de categorías...")
    cat_data = _fetch_json(f"{API_BASE}/categories/")
    if not cat_data:
        print("❌ No se pudo conectar con la API de Mercadona")
        return []

    # Extraer IDs de subcategorías de alimentación
    subcategory_requests = []
    for top_cat in cat_data.get("results", []):
        if top_cat["id"] not in FOOD_TOP_IDS:
            continue
        top_name = top_cat["name"]
        for subcat in top_cat.get("categories", []):
            subcategory_requests.append({
                "id": subcat["id"],
                "name": subcat["name"],
                "top_category": top_name,
            })

    print(f"   {len(subcategory_requests)} subcategorías de alimentación encontradas\n")

    all_products = []
    seen_ids = set()
    current_top = ""

    for sub_req in subcategory_requests:
        if sub_req["top_category"] != current_top:
            current_top = sub_req["top_category"]
            print(f"📂 {current_top}")

        # Fetch subcategory detail (contains sub-subcategories with products)
        data = _fetch_json(f"{API_BASE}/categories/{sub_req['id']}/")
        if not data:
            continue

        # Products can be nested in sub-subcategories
        subcats_with_products = data.get("categories", [])
        if not subcats_with_products:
            # Sometimes products are directly in the subcategory
            if data.get("products"):
                subcats_with_products = [data]

        subcat_count = 0
        for subsubcat in subcats_with_products:
            products = subsubcat.get("products", [])
            for prod in products:
                prod_id = str(prod.get("id", ""))
                if prod_id in seen_ids or not prod_id:
                    continue
                seen_ids.add(prod_id)

                display_name = prod.get("display_name", "")
                price_info = prod.get("price_instructions", {})
                unit_price = float(price_info.get("unit_price", 0))
                thumbnail = prod.get("thumbnail", "")
                brand = _extract_brand(display_name)

                all_products.append({
                    "mercadona_id": prod_id,
                    "name": display_name,
                    "brand": brand,
                    "category": sub_req["top_category"],
                    "subcategory": sub_req["name"],
                    "price": unit_price,
                    "unit_size": price_info.get("unit_size", 0),
                    "size_format": price_info.get("size_format", ""),
                    "packaging": prod.get("packaging", ""),
                    "image_url": thumbnail,
                    "share_url": prod.get("share_url", ""),
                })
                subcat_count += 1

        if subcat_count:
            print(f"   └─ {sub_req['name']}: {subcat_count} productos")
        time.sleep(0.2)

    print(f"\n✅ Total: {len(all_products)} productos de alimentación scrapeados")
    return all_products


def populate_database(products: list[dict]) -> int:
    """Inserta los productos scrapeados en la BD, reemplazando los seed data."""
    conn = sqlite3.connect(DB_PATH)

    conn.execute("DROP TABLE IF EXISTS products")
    conn.execute("""
        CREATE TABLE products (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            mercadona_id    TEXT    UNIQUE,
            name            TEXT    NOT NULL,
            brand           TEXT    NOT NULL DEFAULT 'Hacendado',
            category        TEXT    NOT NULL,
            subcategory     TEXT    NOT NULL DEFAULT '',
            price           REAL    NOT NULL,
            unit_size       REAL    DEFAULT 0,
            size_format     TEXT    DEFAULT '',
            packaging       TEXT    DEFAULT '',
            allergens       TEXT    NOT NULL DEFAULT '[]',
            kcal_100g       REAL    DEFAULT 0,
            protein_100g    REAL    DEFAULT 0,
            carbs_100g      REAL    DEFAULT 0,
            fat_100g        REAL    DEFAULT 0,
            image_url       TEXT    DEFAULT '',
            share_url       TEXT    DEFAULT ''
        )
    """)

    inserted = 0
    for p in products:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO products
                (mercadona_id, name, brand, category, subcategory, price,
                 unit_size, size_format, packaging, allergens, image_url, share_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)
            """, (
                p["mercadona_id"], p["name"], p["brand"], p["category"],
                p["subcategory"], p["price"], p["unit_size"],
                p["size_format"], p["packaging"], p["image_url"],
                p["share_url"],
            ))
            inserted += 1
        except Exception as e:
            print(f"  ⚠ Error insertando {p['name']}: {e}")

    conn.commit()
    conn.close()
    print(f"💾 {inserted} productos insertados en {DB_PATH}")
    return inserted


def main():
    print("=" * 60)
    print("  MERCADONA AUTOPILOT — Scraper de Productos")
    print("=" * 60)
    print()

    products = scrape_all_products()

    if not products:
        print("No se obtuvieron productos. Abortando.")
        return

    hacendado = [p for p in products if p["brand"] == "Hacendado"]
    other = [p for p in products if p["brand"] != "Hacendado"]
    print(f"\n📊 Desglose: {len(hacendado)} Hacendado + {len(other)} otras marcas")

    count = populate_database(products)

    print(f"\n🎉 ¡Hecho! {count} productos listos en la base de datos.")
    print(f"   Ruta BD: {DB_PATH}")


if __name__ == "__main__":
    main()
