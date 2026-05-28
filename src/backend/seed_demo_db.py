"""
Genera una base de datos demo curada para presentaciones.
~200 productos realistas con:
  - Alérgenos correctos en español
  - Macronutrientes coherentes (por 100g)
  - Precios realistas de Mercadona (2024-2025)
  - Mayoría marca Hacendado (~70%)
  - Categorías y subcategorías consistentes

Uso:
    python -m src.backend.seed_demo_db
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = str(Path(__file__).resolve().parent / "mercadona.db")

# ═══════════════════════════════════════════════════════════
#  CATÁLOGO DE PRODUCTOS CURADOS
# ═══════════════════════════════════════════════════════════
# Formato por producto:
#   (name, brand, category, subcategory, price, unit_size, size_format, packaging,
#    allergens_list, kcal, protein, carbs, fat)

PRODUCTS = [
    # ─── ARROZ, LEGUMBRES Y PASTA ─────────────────────────
    ("Arroz redondo Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Arroces", 1.25, 1.0, "kg", "Paquete", [], 354, 6.7, 78.0, 0.9),
    ("Arroz redondo SOS", "SOS", "Arroz, legumbres y pasta", "Arroces", 2.15, 1.0, "kg", "Paquete", [], 354, 6.7, 78.0, 0.9),
    ("Arroz basmati Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Arroces", 1.85, 1.0, "kg", "Paquete", [], 350, 7.5, 77.0, 0.6),
    ("Arroz integral Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Arroces", 1.45, 1.0, "kg", "Paquete", [], 362, 7.9, 74.0, 2.7),
    ("Fideos nº3 Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Pastas", 0.82, 0.5, "kg", "Paquete", ["gluten"], 359, 12.5, 72.0, 1.5),
    ("Espaguetis Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Pastas", 0.85, 0.5, "kg", "Paquete", ["gluten"], 356, 12.0, 71.0, 1.8),
    ("Espaguetis Gallo", "Gallo", "Arroz, legumbres y pasta", "Pastas", 1.45, 0.5, "kg", "Paquete", ["gluten"], 356, 12.0, 71.0, 1.8),
    ("Macarrones Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Pastas", 0.82, 0.5, "kg", "Paquete", ["gluten"], 356, 12.0, 71.0, 1.8),
    ("Macarrones sin gluten Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Pastas", 1.55, 0.5, "kg", "Paquete", [], 356, 7.0, 78.0, 1.5),
    ("Macarrones Gallo", "Gallo", "Arroz, legumbres y pasta", "Pastas", 1.35, 0.5, "kg", "Paquete", ["gluten"], 356, 12.0, 71.0, 1.8),
    ("Pasta penne rigate Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Pastas", 0.90, 0.5, "kg", "Paquete", ["gluten"], 355, 12.0, 71.0, 1.5),
    ("Lentejas pardinas Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Legumbres", 1.65, 1.0, "kg", "Paquete", [], 338, 24.0, 52.0, 1.4),
    ("Lentejas pardinas Luengo", "Luengo", "Arroz, legumbres y pasta", "Legumbres", 2.60, 1.0, "kg", "Paquete", [], 338, 24.0, 52.0, 1.4),
    ("Garbanzos Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Legumbres", 1.75, 1.0, "kg", "Paquete", [], 364, 19.3, 55.0, 5.0),
    ("Alubias blancas Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Legumbres", 1.80, 1.0, "kg", "Paquete", [], 329, 21.0, 50.0, 1.6),

    # ─── CARNE ────────────────────────────────────────────
    ("Pechuga de pollo fileteada", "Hacendado", "Carne", "Pollo", 5.25, 0.6, "kg", "Bandeja", [], 110, 23.0, 0.0, 1.5),
    ("Muslos de pollo", "Hacendado", "Carne", "Pollo", 3.10, 1.0, "kg", "Bandeja", [], 185, 17.0, 0.0, 13.0),
    ("Contramuslos de pollo", "Hacendado", "Carne", "Pollo", 3.50, 0.8, "kg", "Bandeja", [], 190, 18.0, 0.0, 13.5),
    ("Carne picada de ternera y cerdo", "Hacendado", "Carne", "Ternera", 4.25, 0.4, "kg", "Bandeja", [], 212, 17.0, 0.5, 15.5),
    ("Filetes de ternera para guisar", "Hacendado", "Carne", "Ternera", 7.90, 0.5, "kg", "Bandeja", [], 150, 21.0, 0.0, 7.0),
    ("Costillas de cerdo adobadas", "Hacendado", "Carne", "Cerdo", 4.50, 0.5, "kg", "Bandeja", [], 250, 18.0, 2.0, 19.0),
    ("Lomo de cerdo en filetes", "Hacendado", "Carne", "Cerdo", 5.95, 0.5, "kg", "Bandeja", [], 143, 22.5, 0.0, 5.5),
    ("Chorizo de guisar Hacendado", "Hacendado", "Carne", "Embutidos", 2.10, 0.3, "kg", "Envase", [], 285, 14.0, 2.0, 24.0),
    ("Salchichas de pollo Hacendado", "Hacendado", "Carne", "Embutidos", 1.55, 0.4, "kg", "Envase", ["gluten"], 180, 13.0, 5.0, 12.0),
    ("Salchichas de pollo Campofrío", "Campofrío", "Carne", "Embutidos", 2.45, 0.4, "kg", "Envase", ["gluten"], 180, 13.0, 5.0, 12.0),
    ("Hamburguesas de vacuno Hacendado", "Hacendado", "Carne", "Hamburguesas", 2.85, 0.32, "kg", "Bandeja", ["gluten"], 220, 16.0, 6.0, 15.0),
    ("Bacon ahumado en lonchas Hacendado", "Hacendado", "Carne", "Embutidos", 1.95, 0.2, "kg", "Envase", [], 270, 15.0, 1.0, 23.0),
    ("Bacon ahumado El Pozo", "El Pozo", "Carne", "Embutidos", 2.75, 0.2, "kg", "Envase", [], 270, 15.0, 1.0, 23.0),
    ("Jamón cocido extra El Pozo", "El Pozo", "Carne", "Embutidos", 2.80, 0.2, "kg", "Envase", [], 110, 18.0, 1.0, 3.5),

    # ─── MARISCO Y PESCADO ────────────────────────────────
    ("Lomos de merluza Hacendado", "Hacendado", "Marisco y pescado", "Pescado fresco", 5.90, 0.4, "kg", "Bandeja", ["pescado"], 82, 17.0, 0.0, 1.3),
    ("Lomos de merluza Pescanova", "Pescanova", "Marisco y pescado", "Pescado fresco", 8.20, 0.4, "kg", "Bandeja", ["pescado"], 82, 17.0, 0.0, 1.3),
    ("Filetes de salmón", "Hacendado", "Marisco y pescado", "Pescado fresco", 7.50, 0.3, "kg", "Bandeja", ["pescado"], 208, 20.0, 0.0, 13.0),
    ("Gambas peladas congeladas Hacendado", "Hacendado", "Marisco y pescado", "Marisco", 5.45, 0.4, "kg", "Bolsa", ["crustáceos"], 85, 18.0, 0.0, 1.0),
    ("Atún claro en aceite de oliva Hacendado", "Hacendado", "Marisco y pescado", "Conservas de pescado", 2.10, 0.24, "kg", "Lata", ["pescado"], 198, 26.0, 0.0, 10.0),
    ("Atún claro en aceite de oliva Calvo", "Calvo", "Marisco y pescado", "Conservas de pescado", 3.45, 0.24, "kg", "Lata", ["pescado"], 198, 26.0, 0.0, 10.0),
    ("Sardinas en aceite de oliva Hacendado", "Hacendado", "Marisco y pescado", "Conservas de pescado", 1.80, 0.12, "kg", "Lata", ["pescado"], 220, 22.0, 0.0, 14.0),
    ("Mejillones en escabeche Hacendado", "Hacendado", "Marisco y pescado", "Conservas de pescado", 2.35, 0.11, "kg", "Lata", ["moluscos"], 170, 18.0, 3.0, 9.0),
    ("Bacalao desalado desmigado Hacendado", "Hacendado", "Marisco y pescado", "Pescado fresco", 4.95, 0.3, "kg", "Bandeja", ["pescado"], 78, 18.0, 0.0, 0.4),
    ("Langostinos cocidos Hacendado", "Hacendado", "Marisco y pescado", "Marisco", 6.50, 0.4, "kg", "Bandeja", ["crustáceos"], 95, 20.0, 0.0, 1.5),

    # ─── FRUTA Y VERDURA ─────────────────────────────────
    ("Tomates pera bandeja", "Hacendado", "Fruta y verdura", "Verduras", 1.65, 0.8, "kg", "Bandeja", [], 18, 0.9, 3.5, 0.2),
    ("Patatas selección", "Hacendado", "Fruta y verdura", "Verduras", 1.49, 2.0, "kg", "Malla", [], 77, 2.0, 17.0, 0.1),
    ("Cebollas", "Hacendado", "Fruta y verdura", "Verduras", 1.15, 1.0, "kg", "Malla", [], 40, 1.1, 9.0, 0.1),
    ("Pimientos rojos", "Hacendado", "Fruta y verdura", "Verduras", 1.95, 0.5, "kg", "Bandeja", [], 31, 1.0, 6.0, 0.3),
    ("Pimientos verdes", "Hacendado", "Fruta y verdura", "Verduras", 1.75, 0.5, "kg", "Bandeja", [], 20, 0.9, 3.7, 0.2),
    ("Lechuga iceberg", "Hacendado", "Fruta y verdura", "Verduras", 0.95, 0.3, "kg", "Bolsa", [], 14, 0.9, 2.0, 0.1),
    ("Lechuga romana", "Hacendado", "Fruta y verdura", "Verduras", 0.89, 0.3, "kg", "Bolsa", [], 17, 1.2, 2.1, 0.3),
    ("Pepino", "Hacendado", "Fruta y verdura", "Verduras", 0.79, 0.4, "kg", "Unidad", [], 15, 0.7, 2.6, 0.1),
    ("Zanahorias", "Hacendado", "Fruta y verdura", "Verduras", 0.89, 1.0, "kg", "Bolsa", [], 41, 0.9, 9.6, 0.2),
    ("Judías verdes planas", "Hacendado", "Fruta y verdura", "Verduras", 2.10, 0.4, "kg", "Bandeja", [], 31, 1.8, 5.0, 0.1),
    ("Calabacín", "Hacendado", "Fruta y verdura", "Verduras", 1.25, 0.5, "kg", "Unidad", [], 17, 1.2, 3.1, 0.3),
    ("Champiñones laminados Hacendado", "Hacendado", "Fruta y verdura", "Verduras", 1.30, 0.25, "kg", "Bandeja", [], 22, 3.1, 0.5, 0.3),
    ("Ajo", "Hacendado", "Fruta y verdura", "Verduras", 1.10, 0.3, "kg", "Malla", [], 149, 6.4, 33.0, 0.5),
    ("Manzanas Golden", "Hacendado", "Fruta y verdura", "Frutas", 1.99, 1.0, "kg", "Malla", [], 52, 0.3, 14.0, 0.2),
    ("Plátanos de Canarias", "Plátano de Canarias", "Fruta y verdura", "Frutas", 1.89, 1.0, "kg", "Manojo", [], 89, 1.1, 23.0, 0.3),
    ("Naranjas de zumo", "Hacendado", "Fruta y verdura", "Frutas", 2.25, 2.0, "kg", "Malla", [], 47, 0.9, 12.0, 0.1),
    ("Fresas", "Hacendado", "Fruta y verdura", "Frutas", 2.50, 0.5, "kg", "Tarrina", [], 33, 0.7, 7.7, 0.3),
    ("Limones", "Hacendado", "Fruta y verdura", "Frutas", 1.39, 0.75, "kg", "Malla", [], 29, 1.1, 9.0, 0.3),
    ("Aguacate", "Hacendado", "Fruta y verdura", "Frutas", 1.95, 0.2, "kg", "Unidad", [], 160, 2.0, 8.5, 14.7),
    ("Espinacas frescas Hacendado", "Hacendado", "Fruta y verdura", "Verduras", 1.50, 0.3, "kg", "Bolsa", [], 23, 2.9, 3.6, 0.4),
    ("Brócoli", "Hacendado", "Fruta y verdura", "Verduras", 1.79, 0.5, "kg", "Unidad", [], 34, 2.8, 6.6, 0.4),
    ("Maíz dulce en grano Hacendado", "Hacendado", "Fruta y verdura", "Verduras", 1.15, 0.3, "kg", "Lata", [], 86, 3.2, 16.0, 1.2),

    # ─── HUEVOS, LECHE Y MANTEQUILLA ─────────────────────
    ("Huevos camperos L Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Huevos", 2.15, 12.0, "ud", "Cartón", ["huevo"], 155, 13.0, 1.1, 11.0),
    ("Huevos frescos M Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Huevos", 1.79, 12.0, "ud", "Cartón", ["huevo"], 155, 13.0, 1.1, 11.0),
    ("Leche entera Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Leche", 0.89, 1.0, "L", "Brik", ["lactosa"], 65, 3.2, 4.8, 3.6),
    ("Leche entera Pascual", "Pascual", "Huevos, leche y mantequilla", "Leche", 1.25, 1.0, "L", "Brik", ["lactosa"], 65, 3.2, 4.8, 3.6),
    ("Leche semidesnatada Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Leche", 0.85, 1.0, "L", "Brik", ["lactosa"], 46, 3.2, 4.8, 1.6),
    ("Leche semidesnatada Pascual", "Pascual", "Huevos, leche y mantequilla", "Leche", 1.15, 1.0, "L", "Brik", ["lactosa"], 46, 3.2, 4.8, 1.6),
    ("Leche sin lactosa Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Leche", 1.05, 1.0, "L", "Brik", [], 46, 3.2, 4.8, 1.6),
    ("Leche sin lactosa Pascual", "Pascual", "Huevos, leche y mantequilla", "Leche", 1.35, 1.0, "L", "Brik", [], 46, 3.2, 4.8, 1.6),
    ("Mantequilla Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Mantequilla", 1.69, 0.25, "kg", "Envase", ["lactosa"], 743, 0.6, 0.8, 82.0),
    ("Mantequilla Arias", "Arias", "Huevos, leche y mantequilla", "Mantequilla", 2.35, 0.25, "kg", "Envase", ["lactosa"], 743, 0.6, 0.8, 82.0),
    ("Nata para cocinar Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Nata", 0.85, 0.2, "L", "Brik", ["lactosa"], 200, 2.4, 3.5, 20.0),
    ("Nata para montar Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Nata", 1.25, 0.5, "L", "Brik", ["lactosa"], 308, 2.2, 3.2, 32.0),
    ("Bebida de avena Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Leche", 1.15, 1.0, "L", "Brik", ["gluten"], 42, 0.3, 8.0, 1.0),
    ("Bebida de avena Alpro", "Alpro", "Huevos, leche y mantequilla", "Leche", 2.05, 1.0, "L", "Brik", ["gluten"], 42, 0.3, 8.0, 1.0),
    ("Bebida de soja Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Leche", 1.19, 1.0, "L", "Brik", ["soja"], 39, 3.3, 2.5, 1.8),

    # ─── CHARCUTERÍA Y QUESOS ─────────────────────────────
    ("Jamón serrano Hacendado", "Hacendado", "Charcutería y quesos", "Jamón", 2.75, 0.2, "kg", "Envase", [], 241, 30.0, 0.0, 13.0),
    ("Jamón cocido extra Hacendado", "Hacendado", "Charcutería y quesos", "Jamón", 1.95, 0.2, "kg", "Envase", [], 110, 18.0, 1.5, 3.5),
    ("Queso rallado mezcla Hacendado", "Hacendado", "Charcutería y quesos", "Quesos", 1.99, 0.2, "kg", "Bolsa", ["lactosa"], 380, 26.0, 0.5, 30.0),
    ("Queso tierno en lonchas Hacendado", "Hacendado", "Charcutería y quesos", "Quesos", 2.15, 0.2, "kg", "Envase", ["lactosa"], 330, 22.0, 0.5, 26.0),
    ("Queso manchego semicurado", "García Baquero", "Charcutería y quesos", "Quesos", 3.85, 0.25, "kg", "Cuña", ["lactosa"], 392, 28.0, 0.5, 31.0),
    ("Mozzarella fresca Hacendado", "Hacendado", "Charcutería y quesos", "Quesos", 1.45, 0.125, "kg", "Envase", ["lactosa"], 280, 18.0, 1.0, 22.0),
    ("Queso crema para untar Hacendado", "Hacendado", "Charcutería y quesos", "Quesos", 1.35, 0.2, "kg", "Tarrina", ["lactosa"], 245, 5.5, 3.5, 24.0),
    ("Salchichón extra Hacendado", "Hacendado", "Charcutería y quesos", "Embutidos", 2.45, 0.2, "kg", "Envase", [], 380, 24.0, 1.0, 31.0),
    ("Fuet extra Hacendado", "Hacendado", "Charcutería y quesos", "Embutidos", 1.85, 0.15, "kg", "Envase", [], 420, 27.0, 2.0, 34.0),
    ("Pavo en lonchas Hacendado", "Hacendado", "Charcutería y quesos", "Fiambres", 1.75, 0.2, "kg", "Envase", [], 105, 17.0, 2.0, 3.0),

    # ─── ACEITE, ESPECIAS Y SALSAS ────────────────────────
    ("Aceite de oliva virgen extra Hacendado", "Hacendado", "Aceite, especias y salsas", "Aceites", 4.95, 1.0, "L", "Botella", [], 900, 0.0, 0.0, 100.0),
    ("Aceite de oliva virgen extra Carbonell", "Carbonell", "Aceite, especias y salsas", "Aceites", 7.95, 1.0, "L", "Botella", [], 900, 0.0, 0.0, 100.0),
    ("Aceite de oliva suave Hacendado", "Hacendado", "Aceite, especias y salsas", "Aceites", 4.10, 1.0, "L", "Botella", [], 900, 0.0, 0.0, 100.0),
    ("Aceite de oliva suave Carbonell", "Carbonell", "Aceite, especias y salsas", "Aceites", 6.85, 1.0, "L", "Botella", [], 900, 0.0, 0.0, 100.0),
    ("Aceite de girasol Hacendado", "Hacendado", "Aceite, especias y salsas", "Aceites", 1.85, 1.0, "L", "Botella", [], 900, 0.0, 0.0, 100.0),
    ("Vinagre de vino Hacendado", "Hacendado", "Aceite, especias y salsas", "Vinagres", 0.69, 0.5, "L", "Botella", [], 4, 0.0, 0.1, 0.0),
    ("Sal fina Hacendado", "Hacendado", "Aceite, especias y salsas", "Especias", 0.42, 1.0, "kg", "Paquete", [], 0, 0.0, 0.0, 0.0),
    ("Pimienta negra molida Hacendado", "Hacendado", "Aceite, especias y salsas", "Especias", 1.55, 0.05, "kg", "Bote", [], 251, 10.0, 38.0, 3.3),
    ("Azafrán molido Hacendado", "Hacendado", "Aceite, especias y salsas", "Especias", 2.35, 0.001, "kg", "Sobre", [], 310, 11.0, 65.0, 5.9),
    ("Pimentón de la Vera ahumado", "Hacendado", "Aceite, especias y salsas", "Especias", 1.69, 0.075, "kg", "Lata", [], 282, 15.0, 34.0, 13.0),
    ("Orégano Hacendado", "Hacendado", "Aceite, especias y salsas", "Especias", 0.95, 0.02, "kg", "Bote", [], 265, 9.0, 49.0, 4.3),
    ("Tomate frito Hacendado", "Hacendado", "Aceite, especias y salsas", "Salsas", 0.99, 0.4, "kg", "Brik", [], 78, 1.2, 8.5, 4.2),
    ("Tomate frito Orlando", "Orlando", "Aceite, especias y salsas", "Salsas", 1.60, 0.4, "kg", "Brik", [], 78, 1.2, 8.5, 4.2),
    ("Tomate triturado Hacendado", "Hacendado", "Aceite, especias y salsas", "Salsas", 0.89, 0.8, "kg", "Brik", [], 30, 1.2, 4.2, 0.2),
    ("Salsa boloñesa Hacendado", "Hacendado", "Aceite, especias y salsas", "Salsas", 1.49, 0.3, "kg", "Tarro", ["gluten"], 95, 5.0, 7.0, 5.0),
    ("Salsa pesto verde Hacendado", "Hacendado", "Aceite, especias y salsas", "Salsas", 1.89, 0.19, "kg", "Tarro", ["lactosa", "frutos_secos"], 330, 5.0, 6.0, 32.0),
    ("Mayonesa Hacendado", "Hacendado", "Aceite, especias y salsas", "Salsas", 1.55, 0.45, "kg", "Bote", ["huevo"], 680, 1.0, 2.5, 75.0),
    ("Mayonesa Hellmann's", "Hellmann's", "Aceite, especias y salsas", "Salsas", 2.85, 0.45, "kg", "Bote", ["huevo"], 680, 1.0, 2.5, 75.0),
    ("Kétchup Hacendado", "Hacendado", "Aceite, especias y salsas", "Salsas", 1.25, 0.34, "kg", "Bote", [], 110, 1.5, 25.0, 0.3),
    ("Kétchup Heinz", "Heinz", "Aceite, especias y salsas", "Salsas", 2.20, 0.34, "kg", "Bote", [], 110, 1.5, 25.0, 0.3),
    ("Mostaza Hacendado", "Hacendado", "Aceite, especias y salsas", "Salsas", 0.99, 0.2, "kg", "Bote", [], 66, 4.0, 5.0, 3.0),

    # ─── PANADERÍA Y PASTELERÍA ───────────────────────────
    ("Pan de molde integral Hacendado", "Hacendado", "Panadería y pastelería", "Pan de molde", 1.15, 0.46, "kg", "Bolsa", ["gluten", "soja"], 247, 11.0, 40.0, 4.5),
    ("Pan de molde blanco Hacendado", "Hacendado", "Panadería y pastelería", "Pan de molde", 0.99, 0.46, "kg", "Bolsa", ["gluten", "lactosa"], 265, 8.5, 48.0, 3.5),
    ("Pan de molde sin gluten Hacendado", "Hacendado", "Panadería y pastelería", "Pan de molde", 2.15, 0.4, "kg", "Bolsa", [], 265, 4.0, 45.0, 4.5),
    ("Pan de hamburguesa Hacendado", "Hacendado", "Panadería y pastelería", "Pan", 1.10, 0.3, "kg", "Bolsa", ["gluten", "huevo", "lactosa", "soja"], 290, 9.0, 50.0, 5.0),
    ("Barra de pan rústica", "Hacendado", "Panadería y pastelería", "Pan", 0.75, 0.25, "kg", "Unidad", ["gluten"], 270, 9.0, 52.0, 1.5),
    ("Tortitas de maíz Hacendado", "Hacendado", "Panadería y pastelería", "Pan", 1.05, 0.13, "kg", "Paquete", [], 385, 7.0, 82.0, 2.5),
    ("Panecillos para bocadillo", "Hacendado", "Panadería y pastelería", "Pan", 0.95, 0.35, "kg", "Bolsa", ["gluten"], 275, 9.5, 52.0, 2.0),
    ("Mermelada de fresa Hacendado", "Hacendado", "Panadería y pastelería", "Mermeladas", 1.29, 0.4, "kg", "Tarro", [], 245, 0.4, 60.0, 0.1),
    ("Mermelada de melocotón Hacendado", "Hacendado", "Panadería y pastelería", "Mermeladas", 1.29, 0.4, "kg", "Tarro", [], 245, 0.3, 60.0, 0.1),

    # ─── CONSERVAS, CALDOS Y CREMAS ───────────────────────
    ("Caldo de pollo Hacendado", "Hacendado", "Conservas, caldos y cremas", "Caldos", 1.15, 1.0, "L", "Brik", ["gluten"], 12, 0.5, 1.4, 0.3),
    ("Caldo de verduras Hacendado", "Hacendado", "Conservas, caldos y cremas", "Caldos", 1.10, 1.0, "L", "Brik", [], 8, 0.2, 1.2, 0.2),
    ("Garbanzos cocidos Hacendado", "Hacendado", "Conservas, caldos y cremas", "Conservas", 0.85, 0.4, "kg", "Tarro", [], 150, 8.0, 22.0, 2.5),
    ("Tomate natural triturado Hacendado", "Hacendado", "Conservas, caldos y cremas", "Conservas", 0.75, 0.8, "kg", "Lata", [], 22, 1.0, 3.5, 0.1),
    ("Guisantes extra finos Hacendado", "Hacendado", "Conservas, caldos y cremas", "Conservas", 1.15, 0.34, "kg", "Lata", [], 68, 5.0, 10.0, 0.5),
    ("Pimientos del piquillo Hacendado", "Hacendado", "Conservas, caldos y cremas", "Conservas", 1.45, 0.2, "kg", "Tarro", [], 25, 1.0, 4.0, 0.2),
    ("Aceitunas rellenas de anchoa Hacendado", "Hacendado", "Conservas, caldos y cremas", "Conservas", 1.10, 0.35, "kg", "Lata", ["pescado"], 140, 1.5, 5.0, 12.0),
    ("Crema de calabaza Hacendado", "Hacendado", "Conservas, caldos y cremas", "Cremas", 1.85, 0.5, "L", "Brik", [], 35, 0.8, 6.0, 0.8),

    # ─── POSTRES Y YOGURES ────────────────────────────────
    ("Yogur natural Hacendado", "Hacendado", "Postres y yogures", "Yogures", 1.25, 0.5, "kg", "Pack", ["lactosa"], 61, 3.3, 5.5, 2.6),
    ("Yogur griego natural Hacendado", "Hacendado", "Postres y yogures", "Yogures", 1.85, 0.5, "kg", "Pack", ["lactosa"], 115, 3.5, 4.5, 9.5),
    ("Yogur de fresa Hacendado", "Hacendado", "Postres y yogures", "Yogures", 1.35, 0.5, "kg", "Pack", ["lactosa"], 82, 2.8, 13.5, 1.5),
    ("Yogur proteínas Hacendado", "Hacendado", "Postres y yogures", "Yogures", 1.99, 0.33, "kg", "Pack", ["lactosa"], 60, 10.0, 4.0, 0.2),
    ("Flan de huevo Hacendado", "Hacendado", "Postres y yogures", "Postres", 1.49, 0.4, "kg", "Pack", ["huevo", "lactosa"], 135, 4.0, 20.0, 4.0),
    ("Natillas de vainilla Hacendado", "Hacendado", "Postres y yogures", "Postres", 1.25, 0.5, "kg", "Pack", ["lactosa", "huevo"], 120, 3.5, 17.0, 3.5),

    # ─── CEREALES Y GALLETAS ──────────────────────────────
    ("Cereales de avena Hacendado", "Hacendado", "Cereales y galletas", "Cereales", 2.15, 0.5, "kg", "Caja", ["gluten"], 372, 13.0, 60.0, 7.0),
    ("Copos de avena Hacendado", "Hacendado", "Cereales y galletas", "Cereales", 1.35, 0.5, "kg", "Paquete", ["gluten"], 367, 12.0, 58.0, 7.5),
    ("Muesli con frutos rojos Hacendado", "Hacendado", "Cereales y galletas", "Cereales", 2.49, 0.5, "kg", "Bolsa", ["gluten", "frutos_secos"], 365, 9.0, 62.0, 7.5),
    ("Galletas María Hacendado", "Hacendado", "Cereales y galletas", "Galletas", 0.89, 0.8, "kg", "Paquete", ["gluten", "huevo", "lactosa"], 440, 7.0, 72.0, 14.0),
    ("Galletas María sin gluten Hacendado", "Hacendado", "Cereales y galletas", "Galletas", 1.95, 0.4, "kg", "Paquete", [], 450, 4.0, 75.0, 15.0),
    ("Galletas digestive Hacendado", "Hacendado", "Cereales y galletas", "Galletas", 1.05, 0.8, "kg", "Paquete", ["gluten", "lactosa"], 470, 7.0, 65.0, 20.0),
    ("Galletas de chocolate Hacendado", "Hacendado", "Cereales y galletas", "Galletas", 1.35, 0.3, "kg", "Paquete", ["gluten", "huevo", "lactosa", "soja"], 495, 6.5, 63.0, 24.0),

    # ─── CONGELADOS ───────────────────────────────────────
    ("Verdura para paella congelada Hacendado", "Hacendado", "Congelados", "Verduras congeladas", 1.85, 0.6, "kg", "Bolsa", [], 30, 1.5, 5.0, 0.3),
    ("Guisantes congelados Hacendado", "Hacendado", "Congelados", "Verduras congeladas", 1.35, 0.75, "kg", "Bolsa", [], 81, 5.4, 14.0, 0.4),
    ("Patatas fritas congeladas Hacendado", "Hacendado", "Congelados", "Patatas congeladas", 1.55, 1.0, "kg", "Bolsa", [], 170, 2.5, 25.0, 6.5),
    ("Pizza 4 quesos Hacendado", "Hacendado", "Congelados", "Pizzas", 2.45, 0.34, "kg", "Caja", ["gluten", "lactosa"], 260, 11.0, 28.0, 11.5),
    ("Pizza barbacoa Hacendado", "Hacendado", "Congelados", "Pizzas", 2.45, 0.34, "kg", "Caja", ["gluten", "lactosa"], 250, 10.0, 30.0, 10.0),
    ("Croquetas de jamón Hacendado", "Hacendado", "Congelados", "Platos preparados", 2.15, 0.5, "kg", "Bolsa", ["gluten", "huevo", "lactosa"], 190, 5.0, 18.0, 11.0),
    ("San Jacobos de jamón y queso Hacendado", "Hacendado", "Congelados", "Platos preparados", 3.25, 0.35, "kg", "Caja", ["gluten", "huevo", "lactosa"], 235, 13.0, 20.0, 11.0),

    # ─── CACAO, CAFÉ E INFUSIONES ─────────────────────────
    ("Café molido natural Hacendado", "Hacendado", "Cacao, café e infusiones", "Café", 3.10, 0.25, "kg", "Paquete", [], 2, 0.1, 0.0, 0.0),
    ("Café molido mezcla Hacendado", "Hacendado", "Cacao, café e infusiones", "Café", 2.95, 0.25, "kg", "Paquete", [], 2, 0.1, 0.0, 0.0),
    ("Cacao soluble Hacendado", "Hacendado", "Cacao, café e infusiones", "Cacao", 2.65, 0.5, "kg", "Bote", ["lactosa"], 375, 5.0, 78.0, 3.5),
    ("Manzanilla Hacendado", "Hacendado", "Cacao, café e infusiones", "Infusiones", 0.85, 0.025, "kg", "Caja", [], 1, 0.0, 0.2, 0.0),
    ("Cápsulas de café espresso Hacendado", "Hacendado", "Cacao, café e infusiones", "Café", 2.25, 0.05, "kg", "Caja", [], 2, 0.1, 0.0, 0.0),

    # ─── AGUA Y REFRESCOS ─────────────────────────────────
    ("Agua mineral Bezoya", "Bezoya", "Agua y refrescos", "Agua", 0.45, 1.5, "L", "Botella", [], 0, 0.0, 0.0, 0.0),
    ("Agua mineral Font Vella", "Font Vella", "Agua y refrescos", "Agua", 0.65, 1.5, "L", "Botella", [], 0, 0.0, 0.0, 0.0),
    ("Agua mineral Hacendado (pack 6)", "Hacendado", "Agua y refrescos", "Agua", 1.20, 9.0, "L", "Pack", [], 0, 0.0, 0.0, 0.0),
    ("Agua mineral Font Vella (pack 6)", "Font Vella", "Agua y refrescos", "Agua", 3.50, 9.0, "L", "Pack", [], 0, 0.0, 0.0, 0.0),
    ("Refresco de naranja Hacendado", "Hacendado", "Agua y refrescos", "Refrescos", 0.79, 2.0, "L", "Botella", [], 42, 0.0, 10.0, 0.0),
    ("Refresco de naranja Fanta", "Fanta", "Agua y refrescos", "Refrescos", 1.85, 2.0, "L", "Botella", [], 42, 0.0, 10.0, 0.0),
    ("Refresco de cola Hacendado", "Hacendado", "Agua y refrescos", "Refrescos", 0.79, 2.0, "L", "Botella", [], 42, 0.0, 10.5, 0.0),
    ("Refresco de cola Coca-Cola", "Coca-Cola", "Agua y refrescos", "Refrescos", 2.10, 2.0, "L", "Botella", [], 42, 0.0, 10.5, 0.0),
    ("Tónica Hacendado", "Hacendado", "Agua y refrescos", "Refrescos", 1.55, 1.5, "L", "Pack", [], 34, 0.0, 8.5, 0.0),
    ("Tónica Schweppes", "Schweppes", "Agua y refrescos", "Refrescos", 2.95, 1.5, "L", "Pack", [], 34, 0.0, 8.5, 0.0),

    # ─── ZUMOS ────────────────────────────────────────────
    ("Zumo de naranja exprimido Hacendado", "Hacendado", "Zumos", "Zumo refrigerado", 2.25, 1.0, "L", "Botella", [], 45, 0.7, 10.0, 0.1),
    ("Zumo de piña Hacendado", "Hacendado", "Zumos", "Zumo", 1.25, 1.0, "L", "Brik", [], 52, 0.3, 12.8, 0.1),
    ("Zumo de melocotón Hacendado", "Hacendado", "Zumos", "Zumo", 1.15, 1.0, "L", "Brik", [], 56, 0.4, 13.5, 0.1),

    # ─── BODEGA ───────────────────────────────────────────
    ("Cerveza Hacendado", "Hacendado", "Bodega", "Cervezas", 0.55, 0.33, "L", "Lata", ["gluten"], 42, 0.5, 3.5, 0.0),
    ("Cerveza sin alcohol Hacendado", "Hacendado", "Bodega", "Cervezas", 0.59, 0.33, "L", "Lata", ["gluten"], 24, 0.3, 5.0, 0.0),
    ("Vino tinto Crianza Hacendado", "Hacendado", "Bodega", "Vinos tintos", 3.25, 0.75, "L", "Botella", [], 85, 0.1, 2.5, 0.0),
    ("Vino blanco Verdejo Hacendado", "Hacendado", "Bodega", "Vinos blancos", 2.85, 0.75, "L", "Botella", [], 82, 0.1, 2.0, 0.0),

    # ─── AZÚCAR, CARAMELOS Y CHOCOLATE ────────────────────
    ("Chocolate con leche Hacendado", "Hacendado", "Azúcar, caramelos y chocolate", "Chocolate", 1.15, 0.15, "kg", "Tableta", ["gluten", "lactosa", "soja"], 535, 7.0, 56.0, 31.0),
    ("Chocolate negro 72% Hacendado", "Hacendado", "Azúcar, caramelos y chocolate", "Chocolate", 1.25, 0.1, "kg", "Tableta", ["soja"], 540, 8.0, 35.0, 42.0),
    ("Azúcar blanco Hacendado", "Hacendado", "Azúcar, caramelos y chocolate", "Azúcar", 1.09, 1.0, "kg", "Paquete", [], 400, 0.0, 100.0, 0.0),
    ("Miel milflores Hacendado", "Hacendado", "Azúcar, caramelos y chocolate", "Miel", 3.25, 0.5, "kg", "Tarro", [], 304, 0.3, 76.0, 0.0),
    ("Nocilla original", "Nocilla", "Azúcar, caramelos y chocolate", "Cremas untables", 3.15, 0.38, "kg", "Tarro", ["gluten", "lactosa", "frutos_secos", "soja"], 545, 5.0, 58.0, 32.0),

    # ─── APERITIVOS ───────────────────────────────────────
    ("Patatas fritas lisas Hacendado", "Hacendado", "Aperitivos", "Patatas fritas", 1.25, 0.15, "kg", "Bolsa", [], 536, 6.0, 50.0, 35.0),
    ("Patatas fritas lisas Lays", "Lays", "Aperitivos", "Patatas fritas", 2.15, 0.15, "kg", "Bolsa", [], 536, 6.0, 50.0, 35.0),
    ("Frutos secos variados Hacendado", "Hacendado", "Aperitivos", "Frutos secos", 3.25, 0.2, "kg", "Bolsa", ["frutos_secos"], 607, 20.0, 17.0, 52.0),
    ("Almendras tostadas Hacendado", "Hacendado", "Aperitivos", "Frutos secos", 2.85, 0.2, "kg", "Bolsa", ["frutos_secos"], 598, 21.0, 10.0, 52.0),
    ("Aceitunas verdes manzanilla Hacendado", "Hacendado", "Aperitivos", "Aceitunas", 1.35, 0.4, "kg", "Tarro", [], 130, 1.0, 1.0, 13.5),

    # ─── PIZZAS Y PLATOS PREPARADOS ───────────────────────
    ("Masa de pizza refrigerada Hacendado", "Hacendado", "Pizzas y platos preparados", "Masas", 1.35, 0.26, "kg", "Envase", ["gluten", "huevo", "lactosa"], 280, 8.0, 45.0, 7.0),
    ("Masa de pizza sin gluten Hacendado", "Hacendado", "Pizzas y platos preparados", "Masas", 2.25, 0.26, "kg", "Envase", [], 275, 2.0, 48.0, 7.5),
    ("Tortilla de patatas refrigerada Hacendado", "Hacendado", "Pizzas y platos preparados", "Platos preparados", 2.35, 0.6, "kg", "Bandeja", ["huevo"], 140, 5.5, 15.0, 6.0),
    ("Empanadillas de atún congeladas Hacendado", "Hacendado", "Pizzas y platos preparados", "Platos preparados", 2.50, 0.5, "kg", "Bolsa", ["gluten", "huevo", "pescado"], 200, 7.0, 25.0, 8.0),
    ("Lasaña boloñesa Hacendado", "Hacendado", "Pizzas y platos preparados", "Platos preparados", 3.25, 0.5, "kg", "Bandeja", ["gluten", "huevo", "lactosa"], 150, 8.0, 15.0, 6.0),

    # ─── BEBÉ ─────────────────────────────────────────────
    ("Potito de pollo con arroz Hacendado", "Hacendado", "Bebé", "Potitos", 1.05, 0.25, "kg", "Tarro", [], 65, 3.0, 8.0, 2.0),

    # ─── PRODUCTOS EXTRA (para variedad de recetas) ───────
    ("Harina de trigo Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Harinas", 0.69, 1.0, "kg", "Paquete", ["gluten"], 364, 10.0, 73.0, 1.5),
    ("Harina de maíz Hacendado", "Hacendado", "Arroz, legumbres y pasta", "Harinas", 1.15, 0.5, "kg", "Paquete", [], 361, 7.0, 76.0, 2.0),
    ("Leche condensada Hacendado", "Hacendado", "Huevos, leche y mantequilla", "Leche", 1.65, 0.37, "kg", "Bote", ["lactosa"], 321, 8.5, 54.0, 8.0),
    ("Levadura en polvo Hacendado", "Hacendado", "Aceite, especias y salsas", "Especias", 0.75, 0.04, "kg", "Sobre", [], 160, 5.0, 28.0, 2.0),
    ("Cilantro fresco", "Hacendado", "Fruta y verdura", "Verduras", 0.85, 0.03, "kg", "Envase", [], 23, 2.1, 3.7, 0.5),
    ("Perejil fresco", "Hacendado", "Fruta y verdura", "Verduras", 0.79, 0.03, "kg", "Envase", [], 36, 3.0, 6.0, 0.8),
    ("Albahaca fresca", "Hacendado", "Fruta y verdura", "Verduras", 0.99, 0.03, "kg", "Envase", [], 23, 3.2, 2.7, 0.6),

    # ─── PRODUCTOS SALUDABLES / FITNESS / NUEVOS ──────────
    ("Tofu firme", "Hacendado", "Frescos", "Alternativas vegetales", 2.25, 0.4, "kg", "Envase", ["soja"], 135, 14.0, 1.5, 8.0),
    ("Seitán", "Hacendado", "Frescos", "Alternativas vegetales", 2.50, 0.3, "kg", "Envase", ["gluten", "soja"], 120, 24.0, 4.0, 1.5),
    ("Tomates cherry", "Hacendado", "Fruta y verdura", "Verduras", 1.45, 0.5, "kg", "Tarrina", [], 18, 0.9, 3.5, 0.2),
    ("Nueces peladas", "Hacendado", "Aperitivos", "Frutos secos", 2.85, 0.2, "kg", "Bolsa", ["frutos_secos"], 654, 15.0, 13.0, 65.0),
    ("Crema de cacahuete 100%", "Hacendado", "Azúcar, caramelos y chocolate", "Cremas untables", 2.95, 0.5, "kg", "Tarro", ["frutos_secos"], 618, 30.0, 12.0, 50.0),
    ("Tortitas de arroz", "Hacendado", "Cereales y galletas", "Dietéticos", 1.15, 0.13, "kg", "Paquete", [], 385, 8.0, 81.0, 2.5),
    ("Edamame congelado", "Hacendado", "Congelados", "Verduras congeladas", 1.65, 0.5, "kg", "Bolsa", ["soja"], 121, 11.0, 9.0, 5.0),
    ("Arándanos frescos", "Hacendado", "Fruta y verdura", "Frutas", 2.25, 0.2, "kg", "Tarrina", [], 57, 0.7, 14.0, 0.3),
    ("Hummus de garbanzo", "Hacendado", "Charcutería y quesos", "Platos preparados", 1.35, 0.24, "kg", "Tarrina", ["sésamo"], 300, 7.5, 12.0, 24.0),
    ("Guacamole fresco", "Hacendado", "Charcutería y quesos", "Platos preparados", 1.75, 0.2, "kg", "Tarrina", [], 160, 2.0, 8.0, 14.0),
    ("Queso fresco batido desnatado", "Hacendado", "Postres y yogures", "Yogures", 1.45, 0.5, "kg", "Tarrina", ["lactosa"], 48, 8.0, 3.5, 0.1),
    ("Mix de frutos secos natural", "Hacendado", "Aperitivos", "Frutos secos", 2.75, 0.2, "kg", "Bolsa", ["frutos_secos"], 620, 18.0, 15.0, 55.0),
    ("Semillas de chía", "Hacendado", "Aperitivos", "Dietéticos", 1.65, 0.15, "kg", "Bolsa", [], 486, 16.0, 42.0, 30.0),
    ("Kéfir natural", "Hacendado", "Postres y yogures", "Yogures", 1.35, 0.5, "kg", "Botella", ["lactosa"], 45, 3.3, 4.0, 1.5),
    ("Quinoa", "Hacendado", "Arroz, legumbres y pasta", "Arroces", 2.45, 0.5, "kg", "Paquete", [], 368, 14.0, 64.0, 6.0),
]


def create_database():
    """Crea la BD demo desde cero con productos curados."""
    print("=" * 60)
    print("  GENERANDO BASE DE DATOS DEMO CURADA")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)

    # Borrar tabla existente
    conn.execute("DROP TABLE IF EXISTS products")

    # Crear tabla
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
            share_url       TEXT    DEFAULT '',
            days_to_expiry  INTEGER DEFAULT 180
        )
    """)

    # Caducidad realista por categoría/subcategoría
    def _get_expiry(category, subcategory):
        sub_l = subcategory.lower()
        cat_l = category.lower()
        # Productos frescos: 3-7 días
        if cat_l == "carne":
            return 4 if "embutidos" not in sub_l else 21
        if cat_l == "marisco y pescado":
            if "conservas" in sub_l:
                return 730
            return 3
        if cat_l == "fruta y verdura":
            return 7
        # Lácteos y huevos: 15-28 días
        if cat_l == "huevos, leche y mantequilla":
            if "huevos" in sub_l:
                return 21
            return 14
        if cat_l == "postres y yogures":
            return 18
        if cat_l == "charcutería y quesos":
            if "quesos" in sub_l:
                return 30
            return 25
        # Panadería fresca: 5 días
        if cat_l == "panadería y pastelería":
            if "mermelada" in sub_l:
                return 365
            return 5
        # Congelados: 180 días
        if cat_l == "congelados":
            return 180
        # Conservas, salsas, despensa: 365-730 días
        if cat_l in ("conservas, caldos y cremas", "aceite, especias y salsas"):
            return 540
        if cat_l in ("arroz, legumbres y pasta", "cereales y galletas"):
            return 365
        if cat_l in ("azúcar, caramelos y chocolate", "cacao, café e infusiones"):
            return 365
        if cat_l in ("aperitivos",):
            return 180
        # Bebidas
        if cat_l in ("agua y refrescos", "zumos", "bodega"):
            return 180 if "zumo" not in sub_l.lower() else 10
        # Platos preparados refrigerados
        if cat_l == "pizzas y platos preparados":
            return 7
        # Default
        return 180

    inserted = 0
    for i, p in enumerate(PRODUCTS, start=1):
        name, brand, category, subcategory, price, unit_size, size_format, packaging, allergens, kcal, protein, carbs, fat = p

        mercadona_id = f"DEMO-{i:04d}"
        allergens_json = json.dumps(allergens, ensure_ascii=False)
        expiry = _get_expiry(category, subcategory)

        conn.execute("""
            INSERT INTO products
            (mercadona_id, name, brand, category, subcategory, price,
             unit_size, size_format, packaging, allergens,
             kcal_100g, protein_100g, carbs_100g, fat_100g, image_url, days_to_expiry)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mercadona_id, name, brand, category, subcategory, price,
            unit_size, size_format, packaging, allergens_json,
            kcal, protein, carbs, fat, "", expiry,
        ))
        inserted += 1

    conn.commit()

    # ── Resumen ──────────────────────────────────────────
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) as c FROM products").fetchone()["c"]
    hacendado = conn.execute("SELECT COUNT(*) as c FROM products WHERE brand = 'Hacendado'").fetchone()["c"]
    with_allergens = conn.execute("SELECT COUNT(*) as c FROM products WHERE allergens != '[]'").fetchone()["c"]
    with_macros = conn.execute("SELECT COUNT(*) as c FROM products WHERE kcal_100g > 0").fetchone()["c"]

    cats = conn.execute("SELECT category, COUNT(*) as c FROM products GROUP BY category ORDER BY c DESC").fetchall()

    print(f"\n[OK] {inserted} productos insertados en {DB_PATH}")
    print(f"\n📊 Resumen:")
    print(f"   Total: {total}")
    print(f"   Hacendado: {hacendado} ({hacendado*100//total}%)")
    print(f"   Con alérgenos: {with_allergens} ({with_allergens*100//total}%)")
    print(f"   Con macros: {with_macros} ({with_macros*100//total}%)")
    print(f"\n📂 Categorías:")
    for r in cats:
        print(f"   {r['category']}: {r['c']}")

    # Verificar recetas clave
    print(f"\n🧪 Verificación de recetas:")
    recipes = {
        "Paella": ["arroz", "pollo", "verdura", "aceite", "azafrán"],
        "Tortilla": ["huevo", "patata", "aceite", "cebolla"],
        "Ensalada": ["lechuga", "tomate", "atún", "aceite", "maíz"],
        "Pasta boloñesa": ["pasta", "carne", "tomate", "queso"],
        "Hamburguesa": ["hamburguesa", "pan", "lechuga", "tomate", "queso"],
    }
    for recipe, ingredients in recipes.items():
        found = 0
        for ing in ingredients:
            row = conn.execute(
                "SELECT name FROM products WHERE LOWER(name) LIKE ? LIMIT 1",
                (f"%{ing}%",)
            ).fetchone()
            if row:
                found += 1
        status = "✅" if found == len(ingredients) else f"⚠️ {found}/{len(ingredients)}"
        print(f"   {recipe}: {status}")

    conn.close()
    print(f"\n🎉 ¡Base de datos demo lista!")


if __name__ == "__main__":
    create_database()
