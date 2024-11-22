const photoInput = document.getElementById('photoInput');
const previewContainer = document.getElementById('previewContainer');
const form = document.getElementById('uploadForm');
const submitBtn = document.getElementById('submitBtn');

function triggerFileInput(source) {
    photoInput.removeAttribute('capture');
    if (source === 'camera') {
        photoInput.setAttribute('capture', 'camera');
    }
    photoInput.click();
}

// Modificar el input para aceptar múltiples archivos
photoInput.setAttribute('multiple', 'true');
photoInput.setAttribute('name', 'photos');

photoInput.addEventListener('change', function(evt) {
    const files = evt.target.files;
    
    if (files.length > 0) {
        previewContainer.innerHTML = '';
        
        Array.from(files).forEach((file, index) => {
            const previewWrapper = document.createElement('div');
            previewWrapper.className = 'preview-wrapper';
            
            const previewImg = document.createElement('img');
            previewImg.className = 'preview-img';
            
            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-btn';
            removeBtn.innerHTML = '×';
            removeBtn.onclick = function(e) {
                e.preventDefault();
                previewWrapper.remove();
                
                const dt = new DataTransfer();
                const remaining_files = Array.from(photoInput.files).filter((f, i) => i !== index);
                remaining_files.forEach(file => dt.items.add(file));
                photoInput.files = dt.files;
                
                if (photoInput.files.length === 0) {
                    submitBtn.disabled = true;
                    previewContainer.style.display = 'none';
                }
            };
            
            const reader = new FileReader();
            reader.onload = function(e) {
                previewImg.src = e.target.result;
            };
            reader.readAsDataURL(file);
            
            previewWrapper.appendChild(previewImg);
            previewWrapper.appendChild(removeBtn);
            previewContainer.appendChild(previewWrapper);
        });
        
        previewContainer.style.display = 'flex';
        submitBtn.disabled = false;
    } else {
        previewContainer.style.display = 'none';
        submitBtn.disabled = true;
    }
});

form.addEventListener('submit', function(e) {
    if (!photoInput.files || photoInput.files.length === 0) {
        e.preventDefault();
        alert('Por favor selecciona al menos una foto');
    }
});

submitBtn.disabled = true;

// Protecciones
document.addEventListener('contextmenu', function(e) {
    e.preventDefault();
    return false;
});

document.addEventListener('keydown', function(e) {
    if (
        (e.ctrlKey && e.keyCode == 83) ||
        (e.ctrlKey && e.keyCode == 85) ||
        e.keyCode == 123 ||
        (e.ctrlKey && e.shiftKey && e.keyCode == 73) ||
        (e.ctrlKey && e.shiftKey && e.keyCode == 67)
    ) {
        e.preventDefault();
        return false;
    }
});

document.addEventListener('dragstart', function(e) {
    e.preventDefault();
    return false;
});

document.addEventListener('copy', function(e) {
    e.preventDefault();
    return false;
});

document.addEventListener('contextmenu', function(e) {
    e.preventDefault();
    Toastify({
        text: "Las fotografías están protegidas contra copia",
        duration: 3000,
        gravity: "top", 
        position: "right", 
        backgroundColor: "linear-gradient(to right, #ff5f6d, #ffc371)",
        stopOnFocus: true
    }).showToast();
    return false;
});


// Función para crear el HTML de una foto
function createPhotoHTML(photo) {
    return `
        <div class="photo-container">
            <img 
                src="/uploads/${photo.filename}" 
                alt="Foto subida"
                ondragstart="return false;"
                onselectstart="return false;"
                oncontextmenu="return false;"
            >
            
        </div>
    `;
}

// Función para formatear la fecha (similar al filtro de Jinja2)
function formatDateTime(value) {
    try {
        const [date, time] = value.split('_');
        const year = date.slice(0, 4);
        const month = date.slice(4, 6);
        const day = date.slice(6, 8);
        const hour = time.slice(0, 2);
        const minute = time.slice(2, 4);
        return `${day}/${month}/${year} ${hour}:${minute}`;
    } catch {
        return value;
    }
}

// Configurar SSE
const evtSource = new EventSource('/photo-updates');
const gallery = document.querySelector('.gallery');

evtSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    // Actualizar la galería solo si hay cambios
    if (data.photos && data.photos.length > 0) {
        gallery.innerHTML = data.photos.map(createPhotoHTML).join('');
    }
};

evtSource.onerror = function(err) {
    console.error("EventSource failed:", err);
    evtSource.close();
    // Reconectar después de 5 segundos
    setTimeout(() => {
        window.location.reload();
    }, 5000);
};