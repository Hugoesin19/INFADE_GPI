from src.backend.database import search_products_smart
print("Arroz bomba:")
for p in search_products_smart("Arroz bomba", limit=3):
    print(" ", p["name"], p["subcategory"])

print("\nSal marina:")
for p in search_products_smart("Sal marina fina Hacendado", limit=3):
    print(" ", p["name"], p["subcategory"])
