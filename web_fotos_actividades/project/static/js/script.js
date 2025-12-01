document.addEventListener('DOMContentLoaded', () => {
    // Elementos para la página de carga inicial
    const fileInput = document.getElementById('file-upload');
    const fileNameDisplay = document.getElementById('file-name');
    const submitButton = document.getElementById('submit-button');
    const loaderContainer = document.querySelector('.loader-container');
    const container = document.querySelector('.container');

    // Elementos para la página de resultados (si existen)
    const redrawForm = document.getElementById('redraw-form');
    const resultCard = document.querySelector('.result-card');
    const redrawButton = document.querySelector('.btn-sorteo');

    // Funcionalidad de la página de carga inicial
    if (fileInput && fileNameDisplay && submitButton) {
        // Muestra el nombre del archivo seleccionado
        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                fileNameDisplay.textContent = file.name;
                submitButton.disabled = false;
            } else {
                fileNameDisplay.textContent = 'Ningún archivo seleccionado';
                submitButton.disabled = true;
            }
        });

        // Manejo de la acción de enviar el formulario sin recargar la página
        const form = document.getElementById('upload-form');
        form.addEventListener('submit', function (e) {
            e.preventDefault();  // Evita que el formulario se envíe de forma tradicional

             // Hide the text content but keep the container structure
    const sorteoCard = container.querySelector('.sorteo-card');
    if (sorteoCard) {
        sorteoCard.style.display = 'none';
    }
    
    // Show the loader
    loaderContainer.style.display = 'flex';
            // Simula un retraso de 2 segundos antes de enviar el formulario
            setTimeout(() => {
                // Crea un FormData para enviar los archivos
                const formData = new FormData(form);

                // Envío del formulario usando AJAX
                fetch(window.location.href, {
                    method: 'POST',
                    body: formData
                })
                .then(response => {
                    if (response.status === 200) {
                        window.location.href = '/result';  // Redirigir a la página de resultados
                    } else {
                        // En caso de error, restaurar contenido original
                        container.innerHTML = originalContent;
                        loaderContainer.style.display = 'none';
                        throw new Error('Error en el servidor');
                    }
                })
                .catch(error => {
                    console.error('Error al realizar el sorteo:', error);
                    container.innerHTML = originalContent;
                    loaderContainer.style.display = 'none';
                    alert('Hubo un error, por favor intenta de nuevo.');
                });
            }, 2000);  // Retraso de 2 segundos antes de enviar el formulario
        });
    }

    // Funcionalidad de la página de resultados
    if (redrawForm && resultCard && redrawButton) {
        // Manejar el sorteo nuevamente
        redrawForm.addEventListener('submit', function (e) {
            e.preventDefault();  // Evitar envío tradicional del formulario

            // Deshabilitar botón para evitar múltiples clics
            redrawButton.disabled = true;

            // Asegurarnos de que el loader se vea
            loaderContainer.style.display = 'flex';  // Hacer visible el loader
            resultCard.style.display = 'none';  // Ocultar la tarjeta del ganador mientras se sortea

            // Simular un retraso de 2 segundos antes de enviar
            setTimeout(() => {
                // Enviar formulario usando AJAX
                fetch(window.location.href, {
                    method: 'POST',
                    body: new FormData(redrawForm)
                })
                .then(response => {
                    if (response.status === 200) {
                        // Recargar la página para mostrar nuevo ganador
                        window.location.reload();
                    } else {
                        throw new Error('Error en el servidor');
                    }
                })
                .catch(error => {
                    console.error('Error al realizar el sorteo:', error);
                    
                    // Restaurar botón
                    redrawButton.disabled = false;
                    
                    // Mostrar mensaje de error
                    resultCard.innerHTML = `
                        <h1>¡Ups! Algo salió mal</h1>
                        <p>Hubo un error al seleccionar un nuevo ganador. Por favor, intenta de nuevo.</p>
                    `;
                    
                    alert('Hubo un error, por favor intenta de nuevo.');
                    
                    // Ocultar el loader y mostrar la tarjeta nuevamente
                    loaderContainer.style.display = 'none';
                    resultCard.style.display = 'block';
                });
            }, 10000);  // Retraso de 5 segundos
        });
    }
});