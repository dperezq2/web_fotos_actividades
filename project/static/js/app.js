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
})();
