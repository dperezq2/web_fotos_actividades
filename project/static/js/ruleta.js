// Pantalla de la ruleta. El servidor decide a los ganadores antes de la animación;
// la animación solo los presenta.
(function () {
    'use strict';

    const app = document.getElementById('ruletaApp');
    if (!app) return;

    const sortearUrl = app.dataset.sortearUrl;
    const revelarUrl = app.dataset.revelarUrl;
    const quitarUrl = app.dataset.quitarUrl;
    const maximo = Number(app.dataset.max);

    const stage = document.getElementById('stage');
    const stageName = document.getElementById('stageName');
    const stageMeta = document.getElementById('stageMeta');
    const stagePos = document.getElementById('stagePos');
    const restantesEl = document.getElementById('restantes');
    const numGanadoresEl = document.getElementById('numGanadores');
    const lista = document.getElementById('listaGanadores');
    const sinGanadores = document.getElementById('sinGanadores');
    const estadoTag = document.getElementById('estadoTag');
    const drawBtn = document.getElementById('drawBtn');
    const controls = document.getElementById('controls');
    const cantidadOtra = document.getElementById('cantidadOtra');
    const unoPorUno = document.getElementById('unoPorUno');
    const fullscreenBtn = document.getElementById('fullscreenBtn');

    const lanzarConfeti = window.confetti
        ? window.confetti.create(document.getElementById('confettiCanvas'), { resize: true, useWorker: true })
        : () => {};

    let sorteando = false;

    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    // ---------- Cantidad ----------

    function cantidadElegida() {
        const otra = Number(cantidadOtra && cantidadOtra.value);
        if (otra) return otra;
        const radio = controls.querySelector('input[name=cantidad]:checked');
        return radio ? Number(radio.value) : 1;
    }

    if (cantidadOtra) {
        cantidadOtra.addEventListener('input', () => {
            controls.querySelectorAll('input[name=cantidad]').forEach((r) => { r.checked = false; });
        });
        controls.querySelectorAll('input[name=cantidad]').forEach((r) => {
            r.addEventListener('change', () => { cantidadOtra.value = ''; });
        });
    }

    // ---------- Escenario ----------

    function mostrarMensaje(texto, meta = '') {
        stage.classList.remove('is-spinning', 'is-winner');
        stagePos.hidden = true;
        stageName.textContent = texto;
        stageMeta.textContent = meta;
    }

    function metaDe(w) {
        return [`CUE ${w.cue}`, w.empresa, w.distrito].filter(Boolean).join(' · ');
    }

    // Los nombres pasan rápido y se van frenando hasta detenerse
    async function girar(nombres, duracion) {
        stage.classList.remove('is-winner');
        stage.classList.add('is-spinning');
        stagePos.hidden = true;
        stageMeta.textContent = '';
        const inicio = performance.now();
        let anterior = '';
        while (performance.now() - inicio < duracion) {
            const avance = (performance.now() - inicio) / duracion;
            let nombre = nombres[Math.floor(Math.random() * nombres.length)];
            if (nombres.length > 1 && nombre === anterior) nombre = nombres[(nombres.indexOf(nombre) + 1) % nombres.length];
            stageName.textContent = anterior = nombre;
            await sleep(45 + 300 * avance ** 3);
        }
    }

    function revelar(w) {
        stage.classList.remove('is-spinning');
        // Reinicia la animación de entrada
        stage.classList.remove('is-winner');
        void stage.offsetWidth;
        stage.classList.add('is-winner');
        stagePos.hidden = false;
        stagePos.textContent = `Ganador #${w.posicion}`;
        stageName.textContent = w.nombre;
        stageMeta.textContent = metaDe(w);
        lanzarConfeti({ particleCount: 160, spread: 90, origin: { y: 0.65 }, colors: ['#f5c518', '#ffffff', '#7fd44c', '#2c8503'] });
        setTimeout(() => lanzarConfeti({ particleCount: 80, angle: 60, spread: 60, origin: { x: 0, y: 0.8 } }), 250);
        setTimeout(() => lanzarConfeti({ particleCount: 80, angle: 120, spread: 60, origin: { x: 1, y: 0.8 } }), 400);
    }

    // Avisa al servidor qué ganadores ya se mostraron, para que el mural los agregue
    function marcarRevelados(ids) {
        fetch(revelarUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify({ ids }),
            keepalive: true,
        }).catch(() => {}); // Si falla, el mural los muestra igual pasados unos minutos
    }

    // ---------- Lista de ganadores ----------

    function agregarGanador(w) {
        const li = document.createElement('li');
        li.className = 'winner is-new';
        li.dataset.id = w.id;

        const pos = document.createElement('span');
        pos.className = 'winner__pos';
        pos.textContent = w.posicion;

        const body = document.createElement('div');
        body.className = 'winner__body';
        const name = document.createElement('strong');
        name.className = 'winner__name';
        name.textContent = w.nombre;
        const meta = document.createElement('span');
        meta.className = 'winner__meta';
        meta.textContent = metaDe(w);
        body.append(name, meta);
        li.append(pos, body);

        if (quitarUrl) {
            const form = document.createElement('form');
            form.method = 'post';
            form.action = quitarUrl.replace(/\/0\/quitar$/, `/${w.id}/quitar`);
            form.dataset.confirmTitle = `¿Quitar a ${w.nombre}?`;
            form.dataset.confirmOk = 'Quitar ganador';
            form.dataset.confirm = 'Dejará de ser ganador de este sorteo y volverá a participar en sorteos.';
            form.dataset.confirmDanger = '';
            const button = document.createElement('button');
            button.className = 'btn btn--ghost btn--sm winner__remove';
            button.title = 'Quitar ganador';
            button.setAttribute('aria-label', `Quitar a ${w.nombre}`);
            button.innerHTML = '<i class="fa-solid fa-xmark"></i>';
            form.appendChild(button);
            li.appendChild(form);
        }

        lista.appendChild(li);
        sinGanadores.hidden = true;
        numGanadoresEl.textContent = lista.children.length;
    }

    // ---------- Sortear ----------

    async function sortear() {
        if (sorteando || !drawBtn || drawBtn.disabled) return;
        const cantidad = cantidadElegida();
        if (!Number.isInteger(cantidad) || cantidad < 1 || cantidad > maximo) {
            mostrarMensaje('Cantidad no válida', `Elige entre 1 y ${maximo} ganadores`);
            return;
        }

        sorteando = true;
        drawBtn.disabled = true;
        controls.classList.add('is-busy');

        let data;
        try {
            const response = await fetch(sortearUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ cantidad }),
            });
            data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.mensaje || 'No se pudo sortear');
        } catch (err) {
            mostrarMensaje('No se pudo sortear', err.message === 'Failed to fetch' ? 'Revisa la conexión' : err.message);
            terminar();
            return;
        }

        if (estadoTag && estadoTag.textContent.trim() === 'Sin iniciar') {
            estadoTag.textContent = 'En curso';
            estadoTag.className = 'tag';
        }

        const ganadores = data.ganadores;
        const nombres = data.nombres.length ? data.nombres : ganadores.map((w) => w.nombre);

        if (unoPorUno.checked || ganadores.length === 1) {
            for (let i = 0; i < ganadores.length; i++) {
                await girar(nombres, i === 0 ? 3800 : 2400);
                revelar(ganadores[i]);
                marcarRevelados([ganadores[i].id]);
                agregarGanador(ganadores[i]);
                if (i < ganadores.length - 1) await sleep(2600);
            }
        } else {
            await girar(nombres, 3800);
            revelar({ posicion: 0, nombre: `¡${ganadores.length} ganadores!`, cue: '' });
            stagePos.textContent = `Ganadores #${ganadores[0].posicion}–${ganadores[ganadores.length - 1].posicion}`;
            stageMeta.textContent = 'Revisa la lista de ganadores';
            marcarRevelados(ganadores.map((w) => w.id));
            for (const w of ganadores) {
                agregarGanador(w);
                await sleep(120);
            }
        }

        restantesEl.textContent = data.restantes;
        terminar(data.restantes);
    }

    function terminar(restantes) {
        sorteando = false;
        controls.classList.remove('is-busy');
        drawBtn.disabled = restantes === 0;
        if (restantes === 0) stageMeta.textContent += ' · Ya no quedan participantes';
    }

    if (drawBtn) drawBtn.addEventListener('click', sortear);

    document.addEventListener('keydown', (e) => {
        const enCampo = ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(document.activeElement.tagName)
            && document.activeElement.type !== 'radio' && document.activeElement.type !== 'checkbox';
        if (e.code === 'Space' && !enCampo && drawBtn) {
            e.preventDefault();
            sortear();
        }
    });

    // ---------- Pantalla completa (para proyectar) ----------

    fullscreenBtn.addEventListener('click', () => {
        if (document.fullscreenElement) document.exitFullscreen();
        else app.requestFullscreen().catch(() => {});
    });

    document.addEventListener('fullscreenchange', () => {
        const activo = document.fullscreenElement === app;
        fullscreenBtn.querySelector('i').className = `fa-solid ${activo ? 'fa-compress' : 'fa-expand'}`;
        fullscreenBtn.setAttribute('aria-label', activo ? 'Salir de pantalla completa' : 'Pantalla completa');
    });
})();
