from flask import Flask, request, send_from_directory, render_template, jsonify
from flask import Response
import time
import os
from datetime import datetime
import json
from werkzeug.utils import secure_filename
from utils import allowed_file, get_file_hash, load_photos_registry, save_photos_registry, is_duplicate

app = Flask(__name__)

# Configuración
UPLOAD_FOLDER = 'uploads'
PHOTOS_REGISTRY = 'photos_registry.json'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Agregar esta variable global para trackear la última actualización
last_update_timestamp = time.time()

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.template_filter('format_datetime')
def format_datetime(value):
    try:
        date_obj = datetime.strptime(value, '%Y%m%d_%H%M%S')
        return date_obj.strftime('%d/%m/%Y %H:%M')
    except:
        return value

# Agregar esta nueva ruta para los eventos SSE
@app.route('/photo-updates')
def photo_updates():
    def generate():
        global last_update_timestamp
        previous_timestamp = last_update_timestamp
        
        while True:
            # Verificar si hay nuevas fotos
            current_photos = load_photos_registry()
            if last_update_timestamp > previous_timestamp:
                # Filtrar solo las fotos válidas
                valid_photos = []
                for photo in current_photos:
                    if os.path.exists(os.path.join(UPLOAD_FOLDER, photo['filename'])):
                        valid_photos.append(photo)
                
                # Ordenar por fecha de subida, más recientes primero
                sorted_photos = sorted(valid_photos, key=lambda x: x['upload_date'], reverse=True)
                
                # Enviar los datos como evento SSE
                data = json.dumps({
                    'photos': sorted_photos
                })
                yield f"data: {data}\n\n"
                
                previous_timestamp = last_update_timestamp
            
            time.sleep(2)  # Esperar 2 segundos antes de la siguiente verificación
    
    return Response(generate(), mimetype='text/event-stream')


# Modificar la función upload_file para actualizar el timestamp cuando se suben nuevas fotos
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    global last_update_timestamp
    message = None
    photos_registry = load_photos_registry()
    
    if request.method == 'POST':
        if 'photos' not in request.files:
            message = {'type': 'error', 'text': 'No se seleccionó ningún archivo'}
        else:
            files = request.files.getlist('photos')
            successful_uploads = 0
            
            for file in files:
                if file.filename == '':
                    continue
                    
                if file and allowed_file(file.filename):
                    file_hash = get_file_hash(file)
                    
                    if not is_duplicate(file_hash, photos_registry):
                        original_filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"{timestamp}_{original_filename}"
                        
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(file_path)
                        
                        photo_info = {
                            'filename': filename,
                            'original_name': original_filename,
                            'upload_date': timestamp,
                            'file_path': file_path,
                            'file_hash': file_hash
                        }
                        photos_registry.append(photo_info)
                        successful_uploads += 1
            
                if successful_uploads > 0:
                    save_photos_registry(photos_registry)
                    last_update_timestamp = time.time()  # Actualizar timestamp
                    message = {'type': 'success', 'text': f'¡{successful_uploads} foto(s) subida(s) exitosamente!'}
                else:
                    message = {'type': 'error', 'text': 'No se pudo subir ninguna foto'}

    valid_photos = []
    for photo in photos_registry:
        if os.path.exists(os.path.join(UPLOAD_FOLDER, photo['filename'])):
            valid_photos.append(photo)
    
    if len(valid_photos) != len(photos_registry):
        photos_registry = valid_photos
        save_photos_registry(photos_registry)

    return render_template('index.html', 
                        message=message, 
                        photos=sorted(photos_registry, key=lambda x: x['upload_date'], reverse=True))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
