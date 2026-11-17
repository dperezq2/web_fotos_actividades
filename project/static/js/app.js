// Comportamientos comunes del área con sesión
(function () {
    'use strict';

    // Mostrar u ocultar contraseña
    document.querySelectorAll('[data-toggle-password]').forEach((button) => {
        button.addEventListener('click', () => {
            const input = document.getElementById(button.dataset.togglePassword);
            const show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            button.querySelector('i').className = `fa-solid ${show ? 'fa-eye-slash' : 'fa-eye'}`;
            button.setAttribute('aria-label', show ? 'Ocultar contraseña' : 'Mostrar contraseña');
        });
    });

    // Copiar texto al portapapeles
    document.querySelectorAll('[data-copy]').forEach((button) => {
        button.addEventListener('click', async () => {
            const text = document.getElementById(button.dataset.copy).textContent.trim();
            const original = button.innerHTML;
            try {
                await navigator.clipboard.writeText(text);
                button.innerHTML = '<i class="fa-solid fa-check"></i> Copiada';
            } catch (err) {
                button.innerHTML = 'Selecciónala y cópiala';
            }
            setTimeout(() => { button.innerHTML = original; }, 2000);
        });
    });

    // ---------- Modal de confirmación (reemplaza a window.confirm) ----------

    let modal = null;

    function crearModal() {
        const dialog = document.createElement('dialog');
        dialog.className = 'modal';
        dialog.setAttribute('aria-labelledby', 'modalTitulo');
        dialog.setAttribute('aria-describedby', 'modalMensaje');
        dialog.innerHTML = `
            <form method="dialog" class="modal__box">
                <div class="modal__icon" aria-hidden="true"><i class="fa-solid"></i></div>
                <h2 class="modal__title" id="modalTitulo"></h2>
                <p class="modal__message" id="modalMensaje"></p>
                <div class="modal__actions">
                    <button type="submit" value="cancelar" class="btn btn--outline" data-cancelar>Cancelar</button>
                    <button type="submit" value="confirmar" class="btn" data-confirmar></button>
                </div>
            </form>`;
        // Clic fuera de la caja = cancelar
        dialog.addEventListener('click', (e) => {
            if (e.target === dialog) dialog.close('cancelar');
        });
        document.body.appendChild(dialog);
        return dialog;
    }

    /**
     * Muestra el modal y resuelve true si se confirma.
     * opciones: { titulo, mensaje, confirmar, peligro }
     */
    window.confirmar = function (opciones) {
        modal = modal || crearModal();
        const peligro = Boolean(opciones.peligro);
        modal.classList.toggle('modal--danger', peligro);
        modal.querySelector('.modal__icon i').className =
            `fa-solid ${peligro ? 'fa-triangle-exclamation' : 'fa-circle-question'}`;
        modal.querySelector('.modal__title').textContent = opciones.titulo || '¿Confirmar acción?';
        modal.querySelector('.modal__message').textContent = opciones.mensaje || '';
        const botonOk = modal.querySelector('[data-confirmar]');
        botonOk.textContent = opciones.confirmar || 'Confirmar';
        botonOk.className = `btn ${peligro ? 'btn--danger' : 'btn--primary'}`;

        return new Promise((resolve) => {
            modal.addEventListener('close', () => resolve(modal.returnValue === 'confirmar'), { once: true });
            modal.returnValue = '';
            modal.showModal();
            // Foco en "Cancelar": un Enter accidental no ejecuta la acción
            modal.querySelector('[data-cancelar]').focus();
        });
    };

    // Formularios con data-confirm: se pide confirmación antes de enviarlos.
    // Atributos opcionales: data-confirm-title, data-confirm-ok, data-confirm-danger
    document.addEventListener('submit', async (e) => {
        const form = e.target;
        if (!form.matches('form[data-confirm]') || form.dataset.confirmado) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        const ok = await window.confirmar({
            titulo: form.dataset.confirmTitle,
            mensaje: form.dataset.confirm,
            confirmar: form.dataset.confirmOk,
            peligro: 'confirmDanger' in form.dataset,
        });
        if (ok) {
            form.dataset.confirmado = '1';
            form.submit();
        }
    }, true);

    // Aviso de Bloq Mayús activado en campos de contraseña
    document.querySelectorAll('input[data-capslock]').forEach((input) => {
        const aviso = document.getElementById(input.dataset.capslock);
        const revisar = (e) => {
            if (e.getModifierState) aviso.hidden = !e.getModifierState('CapsLock');
        };
        input.addEventListener('keydown', revisar);
        input.addEventListener('keyup', revisar);
        input.addEventListener('blur', () => { aviso.hidden = true; });
    });

    // Botón en estado "cargando" al enviar (evita doble clic)
    document.querySelectorAll('form[data-loading]').forEach((form) => {
        form.addEventListener('submit', () => {
            const boton = form.querySelector('[type=submit]');
            boton.classList.add('is-loading');
            boton.disabled = true;
        });
    });
    // Al volver con el botón "atrás" del navegador, el botón no debe quedar bloqueado
    window.addEventListener('pageshow', () => {
        document.querySelectorAll('form[data-loading] [type=submit]').forEach((boton) => {
            boton.classList.remove('is-loading');
            boton.disabled = false;
        });
    });

    // ---------- Avisos que se ocultan solos ----------
    // Solo los marcados con data-autohide (mensajes momentáneos). Los errores duran más
    // para alcanzar a leerlos; al pasar el mouse encima se pausan.
    const DURACION_AVISO = { error: 7000, danger: 7000, warning: 7000 };

    function ocultarAviso(alerta) {
        if (alerta.classList.contains('is-hiding')) return;
        alerta.style.height = `${alerta.offsetHeight}px`;
        void alerta.offsetHeight; // Fija la altura antes de animar el cierre
        alerta.classList.add('is-hiding');
        setTimeout(() => alerta.remove(), 350);
    }

    document.querySelectorAll('.alert[data-autohide]').forEach((alerta) => {
        const categoria = (alerta.className.match(/alert--(\w+)/) || [])[1];
        const duracion = Number(alerta.dataset.autohide) || DURACION_AVISO[categoria] || 5000;
        let temporizador = setTimeout(() => ocultarAviso(alerta), duracion);

        alerta.addEventListener('mouseenter', () => clearTimeout(temporizador));
        alerta.addEventListener('mouseleave', () => {
            temporizador = setTimeout(() => ocultarAviso(alerta), 2000);
        });

        const cerrar = document.createElement('button');
        cerrar.type = 'button';
        cerrar.className = 'alert__close';
        cerrar.setAttribute('aria-label', 'Cerrar aviso');
        cerrar.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        cerrar.addEventListener('click', () => ocultarAviso(alerta));
        alerta.classList.add('alert--closable');
        alerta.appendChild(cerrar);

        // En formularios (p. ej. login), el aviso se va en cuanto se vuelve a escribir
        if ('hideOnInput' in alerta.dataset) {
            const form = alerta.parentElement.querySelector('form');
            if (form) form.addEventListener('input', () => ocultarAviso(alerta), { once: true });
        }
    });

    // Mostrar el nombre del archivo elegido
    document.querySelectorAll('input[type=file][data-file-name]').forEach((input) => {
        input.addEventListener('change', () => {
            const target = document.getElementById(input.dataset.fileName);
            target.textContent = input.files.length ? input.files[0].name : 'Ningún archivo seleccionado';
        });
    });

    // ---------- Selector con diseño propio (reemplaza a <datalist>) ----------
    // Permite elegir una opción existente o escribir una nueva. Se filtra al escribir,
    // sin importar mayúsculas ni tildes, y funciona con teclado (↑ ↓ Enter Esc).
    const sinTildes = (texto) => texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

    document.querySelectorAll('[data-combo]').forEach((combo, n) => {
        const input = combo.querySelector('.combo__input');
        const menu = combo.querySelector('.combo__menu');
        const toggle = combo.querySelector('.combo__toggle');
        const existentes = [...menu.querySelectorAll('.combo__option:not([data-nueva])')];
        const nueva = menu.querySelector('[data-nueva]');
        const nuevaTexto = menu.querySelector('[data-nueva-texto]');
        const vacio = menu.querySelector('[data-vacio]');
        [...existentes, nueva].forEach((op, i) => { op.id = `combo${n}-op${i}`; });
        let activa = null;

        const visibles = () => [...menu.querySelectorAll('.combo__option:not([hidden])')];

        function marcarActiva(op) {
            if (activa) activa.classList.remove('is-active');
            activa = op;
            if (op) {
                op.classList.add('is-active');
                op.scrollIntoView({ block: 'nearest' });
                input.setAttribute('aria-activedescendant', op.id);
            } else {
                input.removeAttribute('aria-activedescendant');
            }
        }

        // Muestra las opciones que coinciden; con mostrarTodas (flecha o clic) aparecen todas
        function filtrar(mostrarTodas) {
            const texto = input.value.trim();
            const clave = sinTildes(texto);
            let exacta = false;
            existentes.forEach((op) => {
                const valor = sinTildes(op.dataset.value);
                if (valor === clave) exacta = true;
                op.hidden = !mostrarTodas && clave !== '' && !valor.includes(clave);
                op.setAttribute('aria-selected', String(valor === clave && clave !== ''));
            });
            nueva.hidden = !texto || exacta;
            nuevaTexto.textContent = texto;
            vacio.hidden = existentes.length > 0 || !nueva.hidden;
            marcarActiva(null);
        }

        function abrir(mostrarTodas) {
            filtrar(mostrarTodas);
            const hayAlgo = visibles().length > 0 || !vacio.hidden;
            menu.hidden = !hayAlgo;
            combo.classList.toggle('is-open', hayAlgo);
            input.setAttribute('aria-expanded', String(hayAlgo));
        }

        function cerrar() {
            menu.hidden = true;
            combo.classList.remove('is-open');
            input.setAttribute('aria-expanded', 'false');
            marcarActiva(null);
        }

        function elegir(op) {
            if (op !== nueva) input.value = op.dataset.value;  // "Crear lista" conserva lo escrito
            cerrar();
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }

        input.addEventListener('focus', () => abrir(true));
        input.addEventListener('click', () => { if (menu.hidden) abrir(true); });
        input.addEventListener('input', () => abrir(false));
        input.addEventListener('blur', () => setTimeout(cerrar, 120));

        input.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                if (menu.hidden) abrir(true);
                const lista = visibles();
                if (!lista.length) return;
                const i = lista.indexOf(activa);
                const siguiente = e.key === 'ArrowDown' ? (i + 1) % lista.length : (i <= 0 ? lista.length - 1 : i - 1);
                marcarActiva(lista[siguiente]);
            } else if (e.key === 'Enter' && !menu.hidden && activa) {
                e.preventDefault();  // Elige la opción en lugar de enviar el formulario
                elegir(activa);
            } else if (e.key === 'Escape' && !menu.hidden) {
                e.preventDefault();
                cerrar();
            } else if (e.key === 'Tab') {
                cerrar();
            }
        });

        // mousedown en lugar de click: así el campo no pierde el foco antes de elegir
        menu.addEventListener('mousedown', (e) => {
            e.preventDefault();
            const op = e.target.closest('.combo__option');
            if (op) elegir(op);
        });
        menu.addEventListener('mousemove', (e) => {
            const op = e.target.closest('.combo__option');
            if (op && op !== activa) marcarActiva(op);
        });

        toggle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            if (menu.hidden) { input.focus(); abrir(true); } else { cerrar(); }
        });
    });

    // ---------- Desplegables (<select class="select">) con el mismo diseño ----------
    // El <select> original se queda oculto dentro del formulario: sigue enviando el valor
    // y avisando sus cambios (evento change). Si este código fallara, se ve el nativo.
    document.querySelectorAll('select.select:not([multiple])').forEach((select, n) => {
        const envoltura = document.createElement('div');
        envoltura.className = 'combo combo--select';
        select.parentNode.insertBefore(envoltura, select);
        envoltura.appendChild(select);
        select.classList.add('combo__native');
        select.tabIndex = -1;
        select.setAttribute('aria-hidden', 'true');

        const etiqueta = select.id && document.querySelector(`label[for="${select.id}"]`);
        const boton = document.createElement('button');
        boton.type = 'button';
        boton.className = 'select combo__button';
        boton.disabled = select.disabled;
        boton.setAttribute('aria-haspopup', 'listbox');
        boton.setAttribute('aria-expanded', 'false');
        boton.setAttribute('aria-controls', `select${n}-menu`);
        if (etiqueta) {
            etiqueta.id = etiqueta.id || `select${n}-label`;
            boton.setAttribute('aria-labelledby', `${etiqueta.id} select${n}-valor`);
            // La etiqueta apuntaba al <select> oculto: ahora enfoca el botón
            etiqueta.addEventListener('click', (e) => { e.preventDefault(); boton.focus(); });
        }
        boton.innerHTML = `<span class="combo__value" id="select${n}-valor"></span><i class="fa-solid fa-chevron-down combo__chevron" aria-hidden="true"></i>`;
        const valorVisible = boton.querySelector('.combo__value');

        const menu = document.createElement('ul');
        menu.className = 'combo__menu';
        menu.id = `select${n}-menu`;
        menu.setAttribute('role', 'listbox');
        menu.hidden = true;
        const opciones = [...select.options].map((opcion, i) => {
            const li = document.createElement('li');
            li.className = 'combo__option';
            li.id = `select${n}-op${i}`;
            li.setAttribute('role', 'option');
            li.dataset.value = opcion.value;
            const texto = document.createElement('span');
            texto.className = 'combo__label';
            texto.textContent = opcion.textContent.trim();
            const check = document.createElement('i');
            check.className = 'fa-solid fa-check combo__check';
            check.setAttribute('aria-hidden', 'true');
            li.append(texto, check);
            menu.appendChild(li);
            return li;
        });
        envoltura.append(boton, menu);
        let activa = null;

        function pintarValor() {
            const elegida = select.options[select.selectedIndex];
            valorVisible.textContent = elegida ? elegida.textContent.trim() : '';
            opciones.forEach((li, i) => li.setAttribute('aria-selected', String(i === select.selectedIndex)));
        }

        function marcarActiva(li) {
            if (activa) activa.classList.remove('is-active');
            activa = li;
            if (li) {
                li.classList.add('is-active');
                li.scrollIntoView({ block: 'nearest' });
                boton.setAttribute('aria-activedescendant', li.id);
            } else {
                boton.removeAttribute('aria-activedescendant');
            }
        }

        function abrir() {
            menu.hidden = false;
            envoltura.classList.add('is-open');
            boton.setAttribute('aria-expanded', 'true');
            marcarActiva(opciones[select.selectedIndex] || opciones[0]);
        }

        function cerrar() {
            menu.hidden = true;
            envoltura.classList.remove('is-open');
            boton.setAttribute('aria-expanded', 'false');
            marcarActiva(null);
        }

        function elegir(li) {
            const i = opciones.indexOf(li);
            const cambio = i !== select.selectedIndex;
            select.selectedIndex = i;
            pintarValor();
            cerrar();
            boton.focus();
            if (cambio) select.dispatchEvent(new Event('change', { bubbles: true }));
        }

        boton.addEventListener('click', () => (menu.hidden ? abrir() : cerrar()));

        // Escribir letras salta a la opción que empieza así (como en el nativo)
        let busqueda = '';
        let temporizador = null;

        boton.addEventListener('keydown', (e) => {
            const abierto = !menu.hidden;
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                if (!abierto) { abrir(); return; }
                const i = opciones.indexOf(activa);
                const siguiente = e.key === 'ArrowDown' ? Math.min(i + 1, opciones.length - 1) : Math.max(i - 1, 0);
                marcarActiva(opciones[siguiente]);
            } else if (e.key === 'Home' || e.key === 'End') {
                if (!abierto) return;
                e.preventDefault();
                marcarActiva(opciones[e.key === 'Home' ? 0 : opciones.length - 1]);
            } else if ((e.key === 'Enter' || e.key === ' ') && abierto) {
                e.preventDefault();  // Elige en lugar de enviar el formulario
                if (activa) elegir(activa);
            } else if (e.key === 'Escape' && abierto) {
                e.preventDefault();
                cerrar();
            } else if (e.key === 'Tab') {
                cerrar();
            } else if (e.key.length === 1 && e.key !== ' ' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                busqueda += sinTildes(e.key);
                clearTimeout(temporizador);
                temporizador = setTimeout(() => { busqueda = ''; }, 600);
                const encontrada = opciones.find((li) => sinTildes(li.textContent).startsWith(busqueda));
                if (encontrada) {
                    if (!abierto) abrir();
                    marcarActiva(encontrada);
                }
            }
        });

        menu.addEventListener('mousedown', (e) => e.preventDefault());  // El botón no pierde el foco
        menu.addEventListener('click', (e) => {
            const li = e.target.closest('.combo__option');
            if (li) elegir(li);
        });
        menu.addEventListener('mousemove', (e) => {
            const li = e.target.closest('.combo__option');
            if (li && li !== activa) marcarActiva(li);
        });
        boton.addEventListener('blur', () => setTimeout(() => {
            if (!envoltura.contains(document.activeElement)) cerrar();
        }, 120));

        // Si otro código cambia el <select> (o el navegador lo restaura al volver atrás)
        select.addEventListener('change', pintarValor);
        window.addEventListener('pageshow', pintarValor);
        pintarValor();
    });
})();
