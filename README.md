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

##  Sprints y Evolución del Producto

El desarrollo de *Mercadona Autopilot* se ha estructurado de forma iterativa, pivotando desde un modelo de petición única hacia un asistente conversacional avanzado.

### Sprint 1: Arquitectura Base y Motor Híbrido (V1)
**Objetivo:** Establecer los cimientos de la seguridad alimentaria y el procesamiento de lenguaje natural.
* **Base de Datos:** Estructuración y enriquecimiento de un catálogo de productos con variables nutricionales, alérgenos y fechas de caducidad.
* **Muro Determinista (CSP):** Construcción del embudo de seguridad estricto en Python para garantizar la ausencia de alérgenos y el cumplimiento de dietas.
* **Traductor LLM Inicial:** Primer pipeline capaz de extraer variables de negocio (presupuesto, personas, dieta) a partir de descripciones en lenguaje natural.

### Sprint 2: Enjambre Multi-Agente y UI Estática (V1.5)
**Objetivo:** Generar el carrito óptimo y exponer el proceso de forma transparente al usuario.
* **Enjambre Multi-Agente (LangGraph):** Implementación de la negociación entre el *Agente Nutricionista* (salud), el *Agente Logístico* (stock/caducidad) y el *Agente Financiero* (presupuesto y rentabilidad).
* **Flujo "Petición Única":** Consolidación del modelo donde el usuario lanza un prompt (ej. "Compra sana por 30€") y el sistema devuelve un carrito cerrado sin posibilidad de iterar.
* **Interfaz de Usuario (SPA):** Diseño lineal basado en estados visuales (*Input -> Analizando -> CSP -> Resultados finales*) para aportar feedback visual de las decisiones de la IA.

### Sprint 3: Asistente Conversacional "Mercadín" (V2 - Actual)
**Objetivo:** Pivotar hacia una experiencia proactiva, iterativa y de retención a largo plazo.
* **Identidad de Marca:** Introducción de *Mercadín 🦔*, un asistente IA proactivo que guía todo el flujo de compra.
* **UI de Pantalla Dividida (Split-Pane):** Nueva experiencia de usuario con un chat conversacional a la izquierda y el carrito en vivo actualizándose a la derecha.
* **Modificación Iterativa (Deltas):** Capacidad de aplicar cambios parciales al carrito ("cambia el pollo por salmón") utilizando el CSP de forma incremental, evitando recalcular todo el carrito.
* **Contexto Proactivo:** Motor de recomendaciones basado en señales en tiempo real (hora del día, estación del año, caducidad de inventario) para iniciar la conversación.
* **Memoria Persistente (SQLite):** Implementación de bases de datos relacionales (`chat_sessions`, `purchase_history`) para dotar a la IA de historial de compras y preferencias (alérgenos, presupuesto).
* **Fallback Inteligente (NLP Local):** Motor determinista semántico diseñado para deducir ingredientes y generar platos incluso si la API LLM se queda sin cuota (429 Rate Limit), asegurando alta disponibilidad.

## 📂 Estado 
* [hecho] Repositorio y control de versiones configurado.
* [hecho] Pila del Producto y tablero SCRUM desplegado.
* [hecho] Primeros bocetos de UI finalizados.
* [hecho] Arquitectura de datos definida.
* [hecho] Backend LLM y CSP funcionales.
* [hecho] Interfaz conversacional y carrito dinámico desplegados (Sprint 3).
* [en proceso] Categorización más exacta de productos
