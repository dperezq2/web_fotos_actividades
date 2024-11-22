from flask import Flask, request, send_from_directory, render_template, jsonify
from flask import Response
import time
import os
from datetime import datetime
import json
from werkzeug.utils import secure_filename
from utils import allowed_file, get_file_hash, load_photos_registry, save_photos_registry, is_duplicate

app = Flask(__name__)

# Configuración base
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
last_update_timestamp = time.time()

@app.template_filter('format_datetime')
def format_datetime(value):
    try:
        date_obj = datetime.strptime(value, '%Y%m%d_%H%M%S')
        return date_obj.strftime('%d/%m/%Y %H:%M')
    except:
        return value

def upload_file_with_activity(activity):
    global last_update_timestamp
    message = None
    
    # Configuraciones específicas por actividad
    UPLOAD_FOLDER = f'uploads/{activity}'
    PHOTOS_REGISTRY = f'photos_registry_{activity}.json'
    
    # Crear carpeta si no existe
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
    # Cargar registro de fotos de la actividad
    photos_registry = load_photos_registry(PHOTOS_REGISTRY)
    
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
                        
                        file_path = os.path.join(UPLOAD_FOLDER, filename)
                        file.save(file_path)
                        
                        photo_info = {
                            'filename': filename,
                            'original_name': original_filename,
                            'upload_date': timestamp,
                            'file_path': file_path,
                            'file_hash': file_hash,
                            'activity': activity  # Añade esta línea
                        }
                        photos_registry.append(photo_info)
                        successful_uploads += 1
            
            if successful_uploads > 0:
                save_photos_registry(photos_registry, PHOTOS_REGISTRY)
                last_update_timestamp = time.time()
                message = {'type': 'success', 'text': f'¡{successful_uploads} foto(s) subida(s) exitosamente!'}
            else:
                message = {'type': 'error', 'text': 'No se pudo subir ninguna foto'}

    valid_photos = [
        photo for photo in photos_registry 
        if os.path.exists(os.path.join(UPLOAD_FOLDER, photo['filename']))
    ]
    
    return render_template('index.html', 
                        message=message, 
                        photos=sorted(valid_photos, key=lambda x: x['upload_date'], reverse=True))

@app.route('/cena-gerentes', methods=['GET', 'POST'])
def upload_cena_gerentes():
    return upload_file_with_activity('cena-gerentes')

@app.route('/sesion-gerentes-rrhh', methods=['GET', 'POST'])
def upload_sesion_gerentes_rrhh():
    return upload_file_with_activity('sesion-gerentes-rrhh')

@app.route('/convivio', methods=['GET', 'POST'])
def upload_convivio():
    return upload_file_with_activity('convivio')

@app.route('/actividad-bananero', methods=['GET', 'POST'])
def upload_actividad_bananero():
    return upload_file_with_activity('actividad-bananero')

@app.route('/photo-updates/<activity>')
def photo_updates(activity):
    def generate():
        global last_update_timestamp
        previous_timestamp = last_update_timestamp
        PHOTOS_REGISTRY = f'photos_registry_{activity}.json'
        UPLOAD_FOLDER = f'uploads/{activity}'
        
        while True:
            current_photos = load_photos_registry(PHOTOS_REGISTRY)
            if last_update_timestamp > previous_timestamp:
                valid_photos = [
                    photo for photo in current_photos 
                    if os.path.exists(os.path.join(UPLOAD_FOLDER, photo['filename']))
                ]
                
                sorted_photos = sorted(valid_photos, key=lambda x: x['upload_date'], reverse=True)
                
                data = json.dumps({
                    'photos': sorted_photos
                })
                yield f"data: {data}\n\n"
                
                previous_timestamp = last_update_timestamp
            
            time.sleep(2)
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/uploads/<activity>/<filename>')
def uploaded_file(activity, filename):
    return send_from_directory(f'uploads/{activity}', filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)