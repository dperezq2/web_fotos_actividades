// Página pública de fotografías: cola de subida, galería en vivo y visor.
(function () {
    'use strict';

    const config = {
        uploadUrl: document.body.dataset.uploadUrl,
        apiUrl: document.body.dataset.apiUrl,
        maxBytes: Number(document.body.dataset.maxPhotoMb) * 1024 * 1024,
    };
    const POLL_INTERVAL_MS = 15000;
    const ACCEPTED_TYPES = /^image\/(jpeg|png|webp)$/;
    const ACCEPTED_EXT = /\.(jpe?g|png|webp)$/i;

    const form = document.getElementById('uploadForm');
    const inputs = [document.getElementById('inputCamera'), document.getElementById('inputGallery')];
    const dropzone = document.getElementById('dropzone');
    const queueEl = document.getElementById('queue');
    const submitBtn = document.getElementById('submitBtn');
    const submitLabel = document.getElementById('submitLabel');
    const clearBtn = document.getElementById('clearBtn');
    const gallery = document.getElementById('gallery');
    const photoCount = document.getElementById('photoCount');
    const emptyState = document.getElementById('emptyState');
    const liveIndicator = document.getElementById('liveIndicator');

    let queue = [];
    let uploading = false;
    let nextId = 0;

    // ---------- Avisos ----------

    const toastsEl = document.getElementById('toasts');
    const TOAST_ICONS = {
        success: 'fa-circle-check',
        warning: 'fa-triangle-exclamation',
        error: 'fa-circle-xmark',
        info: 'fa-circle-info',
    };

    function toast(text, type = 'info', duration = 3500) {
        const el = document.createElement('div');
        el.className = `toast toast--${type}`;
        const icon = document.createElement('i');
        icon.className = `fa-solid ${TOAST_ICONS[type]}`;
        const span = document.createElement('span');
        span.textContent = text;
        el.append(icon, span);
        toastsEl.appendChild(el);
        setTimeout(() => {
            el.classList.add('is-leaving');
            setTimeout(() => el.remove(), 300);
        }, duration);
    }

    function plural(n, singular, pluralForm) {
        return `${n} ${n === 1 ? singular : pluralForm}`;
    }

    // ---------- Cola de subida ----------

    function isImage(file) {
        return ACCEPTED_TYPES.test(file.type) || ACCEPTED_EXT.test(file.name);
    }

    function addFiles(fileList) {
        let tooBig = 0;
        let notImage = 0;

        Array.from(fileList).forEach((file) => {
            if (!isImage(file)) { notImage++; return; }
            if (file.size > config.maxBytes) { tooBig++; return; }
            const alreadyQueued = queue.some((item) =>
                item.file.name === file.name && item.file.size === file.size &&
                item.file.lastModified === file.lastModified);
            if (alreadyQueued) return;

            const item = { id: nextId++, file, status: 'pending', previewUrl: URL.createObjectURL(file) };
            item.el = renderQueueItem(item);
            queue.push(item);
            queueEl.appendChild(item.el);
        });

        if (tooBig) toast(`${plural(tooBig, 'foto supera', 'fotos superan')} el máximo de ${document.body.dataset.maxPhotoMb} MB`, 'warning');
        if (notImage) toast(`${plural(notImage, 'archivo no es', 'archivos no son')} una imagen JPG, PNG o WEBP`, 'warning');
        updateQueueUI();
    }

    function renderQueueItem(item) {
        const li = document.createElement('li');
        li.className = 'queue__item';

        const img = document.createElement('img');
        img.src = item.previewUrl;
        img.alt = item.file.name;

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'queue__remove';
        remove.setAttribute('aria-label', `Quitar ${item.file.name}`);
        remove.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        remove.addEventListener('click', () => removeFromQueue(item));

        const status = document.createElement('div');
        status.className = 'queue__status';

        const progress = document.createElement('div');
        progress.className = 'queue__progress';

        li.append(img, remove, status, progress);
        return li;
    }

    const STATUS_VIEW = {
        uploading: { icon: 'fa-spinner fa-spin', text: 'Subiendo…' },
        done: { icon: 'fa-check', text: 'Subida' },
        duplicate: { icon: 'fa-clone', text: 'Ya estaba en la galería' },
        error: { icon: 'fa-rotate-right', text: 'Error' },
    };

    function setItemStatus(item, status, message) {
        item.status = status;
        item.el.className = `queue__item is-${status}`;
        const view = STATUS_VIEW[status];
        const statusEl = item.el.querySelector('.queue__status');
        statusEl.innerHTML = '';
        if (view) {
            const icon = document.createElement('i');
            icon.className = `fa-solid ${view.icon}`;
            const text = document.createElement('span');
            text.textContent = message || view.text;
            statusEl.append(icon, text);
        }
    }

    function setItemProgress(item, fraction) {
        item.el.querySelector('.queue__progress').style.width = `${Math.round(fraction * 100)}%`;
    }

    function removeFromQueue(item) {
        if (uploading) return;
        URL.revokeObjectURL(item.previewUrl);
        item.el.remove();
        queue = queue.filter((q) => q !== item);
        updateQueueUI();
    }

    function pendingItems() {
        return queue.filter((item) => item.status === 'pending' || item.status === 'error');
    }

    function updateQueueUI() {
        const pending = pendingItems().length;
        const retrying = queue.some((item) => item.status === 'error');

        queueEl.hidden = queue.length === 0;
        clearBtn.hidden = queue.length === 0 || uploading;
        submitBtn.disabled = uploading || pending === 0;

        if (uploading) {
            const done = queue.filter((item) => item.status !== 'pending' && item.status !== 'uploading').length;
            submitLabel.textContent = `Subiendo ${Math.min(done + 1, queue.length)} de ${queue.length}…`;
        } else if (pending === 0) {
            submitLabel.textContent = 'Subir fotos';
        } else {
            submitLabel.textContent = `${retrying ? 'Reintentar' : 'Subir'} ${plural(pending, 'foto', 'fotos')}`;
        }
    }

    function uploadOne(item) {
        // Una petición por foto: progreso individual y sin topar el límite por petición de Nginx
        return new Promise((resolve) => {
            const xhr = new XMLHttpRequest();
            const data = new FormData();
            data.append('photos', item.file, item.file.name);

            xhr.open('POST', config.uploadUrl);
            xhr.setRequestHeader('Accept', 'application/json');
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) setItemProgress(item, e.loaded / e.total);
            });
            xhr.addEventListener('load', () => {
                if (xhr.status === 413) {
                    return resolve({ estado: 'error', mensaje: 'Archivo muy grande' });
                }
                try {
                    const body = JSON.parse(xhr.responseText);
                    resolve(body.resultados && body.resultados[0] ? body.resultados[0] : { estado: 'error', mensaje: body.mensaje });
                } catch (err) {
                    resolve({ estado: 'error', mensaje: 'Error del servidor' });
                }
            });
            xhr.addEventListener('error', () => resolve({ estado: 'error', mensaje: 'Sin conexión' }));
            xhr.addEventListener('timeout', () => resolve({ estado: 'error', mensaje: 'Tiempo agotado' }));
            xhr.timeout = 180000;
            xhr.send(data);
        });
    }

    async function uploadQueue() {
        const items = pendingItems();
        if (!items.length || uploading) return;

        uploading = true;
        const totals = { subida: 0, duplicada: 0, error: 0 };

        for (const item of items) {
            setItemStatus(item, 'uploading');
            setItemProgress(item, 0);
            updateQueueUI();

            const result = await uploadOne(item);
            if (result.estado === 'subida') {
                totals.subida++;
                setItemStatus(item, 'done');
                setItemProgress(item, 1);
                if (result.foto) addPhotosToGallery([result.foto]);
            } else if (result.estado === 'duplicada') {
                totals.duplicada++;
                setItemStatus(item, 'duplicate');
            } else {
                totals.error++;
                setItemStatus(item, 'error', result.mensaje);
                setItemProgress(item, 0);
            }
        }

        uploading = false;

        if (totals.subida) toast(`¡${plural(totals.subida, 'foto subida', 'fotos subidas')}!`, 'success');
        if (totals.duplicada) toast(`${plural(totals.duplicada, 'foto ya estaba', 'fotos ya estaban')} en la galería`, 'warning');
        if (totals.error) toast(`${plural(totals.error, 'foto no se pudo', 'fotos no se pudieron')} subir. Toca "Reintentar".`, 'error', 5000);

        // Las subidas y duplicadas salen de la cola tras un momento; los errores quedan para reintentar
        setTimeout(() => {
            queue.filter((item) => item.status === 'done' || item.status === 'duplicate').forEach(removeFromQueue);
        }, 1800);
        updateQueueUI();
    }

    inputs.forEach((input) => {
        input.addEventListener('change', () => {
            addFiles(input.files);
            input.value = ''; // Permite volver a elegir la misma foto y evita enviarla doble
        });
    });

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        if (!pendingItems().length) {
            toast('Primero elige o toma una foto', 'info');
            return;
        }
        uploadQueue();
    });

    clearBtn.addEventListener('click', () => {
        [...queue].forEach(removeFromQueue);
    });

    window.addEventListener('beforeunload', (e) => {
        if (uploading || pendingItems().length) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    // Arrastrar y soltar (escritorio)
    ['dragenter', 'dragover'].forEach((type) => dropzone.addEventListener(type, (e) => {
        e.preventDefault();
        dropzone.classList.add('is-dragover');
    }));
    ['dragleave', 'drop'].forEach((type) => dropzone.addEventListener(type, (e) => {
        e.preventDefault();
        dropzone.classList.remove('is-dragover');
    }));
    dropzone.addEventListener('drop', (e) => {
        if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
    });

    // ---------- Galería ----------

    function createTile(photo) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'tile';
        button.dataset.filename = photo.filename;
        button.dataset.vista = photo.vista;

        const img = document.createElement('img');
        img.src = photo.mini;
        img.alt = 'Foto del evento';
        img.loading = 'lazy';
        img.decoding = 'async';
        img.draggable = false;
        button.appendChild(img);
        return button;
    }

    function tiles() {
        return Array.from(gallery.querySelectorAll('.tile'));
    }

    function updateCount() {
        const total = tiles().length;
        photoCount.textContent = total;
        emptyState.hidden = total > 0;
    }

    // Inserta al inicio las fotos que aún no están en la galería
    function addPhotosToGallery(photos) {
        const known = new Set(tiles().map((t) => t.dataset.filename));
        photos.slice().reverse().forEach((photo) => {
            if (known.has(photo.filename)) return;
            const tile = createTile(photo);
            tile.classList.add('is-new');
            gallery.prepend(tile);
        });
        updateCount();
    }

    // Sincroniza con el servidor conservando los elementos existentes (sin parpadeos)
    function syncGallery(photos) {
        const existing = new Map(tiles().map((t) => [t.dataset.filename, t]));
        const fragment = document.createDocumentFragment();
        photos.forEach((photo) => {
            let tile = existing.get(photo.filename);
            if (!tile) {
                tile = createTile(photo);
                tile.classList.add('is-new');
            }
            fragment.appendChild(tile);
        });
        gallery.replaceChildren(fragment);
        updateCount();
    }

    async function poll() {
        if (document.hidden || uploading) return;
        try {
            const response = await fetch(config.apiUrl, { headers: { Accept: 'application/json' }, cache: 'no-store' });
            if (!response.ok) throw new Error(response.status);
            const data = await response.json();
            const current = tiles().map((t) => t.dataset.filename).join('|');
            const incoming = data.fotos.map((p) => p.filename).join('|');
            if (current !== incoming && !lightboxIsOpen()) syncGallery(data.fotos);
            liveIndicator.classList.remove('is-offline');
        } catch (err) {
            liveIndicator.classList.add('is-offline');
        }
    }

    setInterval(poll, POLL_INTERVAL_MS);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });

    // ---------- Visor ----------

    const lightbox = document.getElementById('lightbox');
    const lbImage = document.getElementById('lbImage');
    const lbSpinner = document.getElementById('lbSpinner');
    const lbCounter = document.getElementById('lbCounter');
    let lbIndex = 0;
    let lastFocused = null;

    function lightboxIsOpen() {
        return !lightbox.hidden;
    }

    function showPhoto(index) {
        const list = tiles();
        if (!list.length) return closeLightbox();
        lbIndex = (index + list.length) % list.length;
        lbSpinner.hidden = false;
        lbImage.style.opacity = '0';
        lbImage.src = list[lbIndex].dataset.vista;
        lbCounter.textContent = `${lbIndex + 1} / ${list.length}`;
    }

    lbImage.addEventListener('load', () => {
        lbSpinner.hidden = true;
        lbImage.style.opacity = '1';
    });
    lbImage.addEventListener('error', () => { lbSpinner.hidden = true; });

    function openLightbox(index) {
        lastFocused = document.activeElement;
        lightbox.hidden = false;
        document.body.style.overflow = 'hidden';
        showPhoto(index);
        document.getElementById('lbClose').focus();
    }

    function closeLightbox() {
        lightbox.hidden = true;
        lbImage.removeAttribute('src');
        document.body.style.overflow = '';
        if (lastFocused) lastFocused.focus();
    }

    gallery.addEventListener('click', (e) => {
        const tile = e.target.closest('.tile');
        if (tile) openLightbox(tiles().indexOf(tile));
    });

    document.getElementById('lbClose').addEventListener('click', closeLightbox);
    document.getElementById('lbPrev').addEventListener('click', () => showPhoto(lbIndex - 1));
    document.getElementById('lbNext').addEventListener('click', () => showPhoto(lbIndex + 1));
    lightbox.addEventListener('click', (e) => {
        if (e.target === lightbox || e.target.classList.contains('lightbox__figure')) closeLightbox();
    });

    document.addEventListener('keydown', (e) => {
        if (!lightboxIsOpen()) return;
        if (e.key === 'Escape') closeLightbox();
        else if (e.key === 'ArrowLeft') showPhoto(lbIndex - 1);
        else if (e.key === 'ArrowRight') showPhoto(lbIndex + 1);
    });

    // Deslizar en celulares
    let touchStartX = null;
    lightbox.addEventListener('touchstart', (e) => { touchStartX = e.changedTouches[0].clientX; }, { passive: true });
    lightbox.addEventListener('touchend', (e) => {
        if (touchStartX === null) return;
        const dx = e.changedTouches[0].clientX - touchStartX;
        if (Math.abs(dx) > 50) showPhoto(lbIndex + (dx < 0 ? 1 : -1));
        touchStartX = null;
    });

    // ---------- Protección básica de las fotos ----------

    document.addEventListener('contextmenu', (e) => {
        if (e.target.closest('.tile, .lightbox')) {
            e.preventDefault();
            toast('Las fotografías están protegidas contra copia', 'info', 2500);
        }
    });

    document.addEventListener('dragstart', (e) => {
        if (e.target.tagName === 'IMG') e.preventDefault();
    });

    document.addEventListener('keydown', (e) => {
        const key = e.key.toLowerCase();
        const blocked = e.key === 'F12' ||
            (e.ctrlKey && (key === 's' || key === 'u')) ||
            (e.ctrlKey && e.shiftKey && (key === 'i' || key === 'c'));
        if (blocked) e.preventDefault();
    });

    updateQueueUI();
})();
