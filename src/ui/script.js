/**
 * Lógica de la SPA - Mercadona Autopilot
 * Simula la interacción con la arquitectura híbrida (LLM + CSP)
 */

document.addEventListener('DOMContentLoaded', () => {
    // Referencias a las secciones y elementos principales
    const heroSection = document.getElementById('hero-section');
    const generateBtn = document.getElementById('generate-btn');
    const consoleSection = document.getElementById('console-section');
    const dashboardSection = document.getElementById('dashboard-section');
    const promptInput = document.getElementById('prompt-input');

    // Pasos secuenciales de la terminal (músculo backend)
    const step1 = document.getElementById('step-1');
    const step2 = document.getElementById('step-2');
    const step3 = document.getElementById('step-3');

    // Event listener principal para generar la cesta
    generateBtn.addEventListener('click', () => {

        // Validación visual básica si el textarea está vacío (Opcional UX)
        if (promptInput.value.trim() === '') {
            promptInput.style.transition = 'none';
            promptInput.style.borderColor = '#ff5f56';
            setTimeout(() => {
                promptInput.style.transition = 'border-color 0.3s';
                promptInput.style.borderColor = 'var(--color-primary)';
            }, 300);
        }

        // 1. Ocultar la sección Hero (Input y botón)
        heroSection.classList.add('hidden');

        // 2. Mostrar la consola de procesamiento
        consoleSection.classList.remove('hidden');

        // Delay base inicial para dar sensación de inicio de proceso
        const inicioDelay = 500;
        const delayEntrePasos = 1500;

        // Mostrar Paso 1: Extracción Multimodal
        setTimeout(() => {
            step1.classList.remove('hidden');
        }, inicioDelay);

        // Mostrar Paso 2: Muro Determinista
        setTimeout(() => {
            step2.classList.remove('hidden');
        }, inicioDelay + delayEntrePasos);

        // Mostrar Paso 3: Enjambre Multi-Agente
        setTimeout(() => {
            step3.classList.remove('hidden');
        }, inicioDelay + (delayEntrePasos * 2));

        // 3. Mostrar el Dashboard de resultados finales (animación fade-in en CSS)
        setTimeout(() => {
            dashboardSection.classList.remove('hidden');

            // Hacer scroll suave hacia los resultados para centrar la atención del usuario
            dashboardSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

        }, inicioDelay + (delayEntrePasos * 3) + 1000); // Dar 1 segundo extra para leer el último OK
    });
});