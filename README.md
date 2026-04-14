# INFADE_GPI
# Mercadona Autopilot


## Equipo
* **Scrum Master:** Edgar Gisbert
* **Product Owner:** Hugo Esclapez
* **Equipo de desarrollo:** Iñaki Aguilar, Malena Belda, Jorge Martínez y Marcos Manén

## Visión del Producto
Convertirnos en el único supermercado que asuma de la carga mental de "El Jefe" al hacer la compra. Utilizamos un motor híbrido de IA para generar cestas personalizadas en segundos, priorizando la rentabilidad (marca Hacendado) y garantizando una seguridad alimentaria estricta.

## Arquitectura Técnica (Híbrida CSP-LLM)
El backend procesa lenguaje natural y lo somete a un embudo de seguridad antes de generar la cesta:
1. **Traductor Multimodal (LLM):** Extracción de variables (presupuesto, alérgenos, macros) desde lenguaje natural.
2. **Muro Determinista (CSP en Python):** Filtrado absoluto de la base de datos para bloquear ingredientes prohibidos o alérgenos.
3. **Enjambre Multi-Agente (LangGraph):** Negociación entre 3 agentes (Nutricionista, Logístico y Financiero) para cuadrar la cesta perfecta y maximizar el margen de beneficio.

## 📂 Estado 
* [hecho] Repositorio y control de versiones configurado.
* [por hacer] Pila del Producto y tablero SCRUM desplegado.
* [hecho] Primeros bocetos de UI finalizados.
* [hecho] Arquitectura de datos definida.
