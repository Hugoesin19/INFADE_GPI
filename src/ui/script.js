const stepsData = [
    { id: 'step1', msg: 'Analizando lenguaje natural...' },
    { id: 'step2', msg: 'Validando restricciones de salud (Muro CSP)...' },
    { id: 'step3', msg: 'Agentes negociando margen y logística...' }
];

const mockItems = [
    { name: 'Pechuga Pollo +Proteína', brand: 'Hacendado', price: '4.50€' },
    { name: 'Pan de Molde Sin Gluten', brand: 'Hacendado', price: '2.80€' },
    { name: 'Hummus de Garbanzos', brand: 'Hacendado', price: '1.45€' },
    { name: 'Cerveza Steinburg (Pack 12)', brand: 'Hacendado', price: '3.60€' },
    { name: 'Papel Higiénico 2 capas', brand: 'Bosque Verde', price: '4.20€' }
];

document.getElementById('mainAction').addEventListener('click', async () => {
    // Reiniciar y mostrar monitor
    const monitor = document.getElementById('techMonitor');
    const results = document.getElementById('resultsSection');
    monitor.classList.remove('hidden');
    results.classList.add('hidden');

    // Simular fases técnicas
    for (let step of stepsData) {
        const el = document.getElementById(step.id);
        el.classList.add('active');
        await new Promise(r => setTimeout(r, 1500));
    }

    // Mostrar resultados finales
    monitor.classList.add('hidden');
    results.classList.remove('hidden');

    // Poblar carrito
    const container = document.getElementById('itemsContainer');
    container.innerHTML = mockItems.map(item => `
        <div class="item-row">
            <div>
                <strong>${item.name}</strong><br>
                <span class="hacendado-label">${item.brand}</span>
            </div>
            <div class="item-price">${item.price}</div>
        </div>
    `).join('');

    // Datos finales basados en el documento
    document.getElementById('resPrice').innerText = '89.85€';
    document.getElementById('resWeight').innerText = '13.2 kg';
    document.getElementById('resSafety').innerText = '100% Sin Gluten';
});