from flask import Flask, request, send_from_directory, render_template, jsonify, Response, url_for, redirect, session
from flask_session import Session
import time
import os
from datetime import datetime
import json
from werkzeug.utils import secure_filename
import requests

from utilidades import allowed_file, get_file_hash, load_photos_registry, save_photos_registry, is_duplicate
from utils.data_loader import validate_photo_path, load_participants
from utils.raffle_logic import perform_raffle

app = Flask(__name__)



# Configurar el almacenamiento de sesiones en el servidor
app.config['SESSION_TYPE'] = 'filesystem'  # O 'redis', 'sqlalchemy', etc.
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_FILE_DIR'] = './.flask_session'  # Carpeta para almacenar las sesiones

app.secret_key = os.urandom(24)  # Necesario para las sesiones
Session(app)  # Inicializar Flask-Session

app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB máximo


# NUEVO: Proxy de imágenes
@app.route('/image-proxy')
def proxy_image():
    # Obtener la URL de la imagen desde los parámetros de la solicitud
    image_url = request.args.get('url')
    
    try:
        # Descargar la imagen
        response = requests.get(image_url, timeout=10)
        
        # Verificar que la descarga fue exitosa
        if response.status_code == 200:
            # Devolver la imagen con el tipo MIME correcto
            return Response(response.content, mimetype=response.headers.get('content-type', 'image/jpeg'))
        else:
            # Si la descarga falla, devolver una imagen por defecto o un error
            return Response('Error al cargar la imagen', status=404)
    
    except requests.RequestException:
        # Manejar errores de solicitud (timeout, conexión, etc.)
        return Response('Error al descargar la imagen', status=500)


@app.route('/sorteo', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Manejo de subida de archivo
        if 'file' not in request.files:
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            return redirect(request.url)
        
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Cargar participantes
            participants = load_participants(filepath)
            
            # Realizar sorteo
            winner = perform_raffle(participants)
            
            # Guardar el ganador y otros datos en la sesión
            session['winner'] = winner
            session['total_participants'] = len(participants)
            session['participants'] = participants  # Guardamos la lista de participantes
            
            # Redirigir a la página de resultados
            return redirect(url_for('result'))
    
    return render_template('index_sorteo.html')


@app.route('/result', methods=['GET', 'POST'])
def result():
    winner = session.get('winner')
    participants = session.get('participants')
    total_participants = session.get('total_participants')

    if not winner or not total_participants:
        return redirect(url_for('index_sorteo'))

    # Si la solicitud es POST, realizar un nuevo sorteo excluyendo al ganador
    if request.method == 'POST':
        if participants:
            # Excluir al ganador de la lista de participantes
            participants = [p for p in participants if p['CUE'] != winner['CUE']]
            
            # Actualizar el total de participantes después de excluir al ganador
            total_participants = len(participants)
            
            # Realizar el sorteo nuevamente
            winner = perform_raffle(participants)
            session['winner'] = winner

            # Guardar el ganador actual en la lista de ganadores anteriores
            previous_winners = session.get('previous_winners', [])
            previous_winners.insert(0, winner)  # Insertar el nuevo ganador al inicio
            session['previous_winners'] = previous_winners[:5]  # Mantener solo los 5 más recientes

            # Guardar los participantes actualizados y el total de participantes
            session['participants'] = participants
            session['total_participants'] = total_participants

            # Redirigir a la misma página para mostrar el nuevo ganador y el contador actualizado
            return redirect(url_for('result'))

    # Extraer la información del ganador
    winner_name = winner.get('Empleado', 'No disponible')
    winner_photo_url = winner.get('PathFotografia', '')

    # Validar la foto del ganador
    if winner_photo_url:
        is_valid_photo = validate_photo_path(winner_photo_url)
        if is_valid_photo:
            # MODIFICACIÓN: Usar el proxy de imágenes
            winner_photo_url = url_for('proxy_image', url=winner_photo_url)
        else:
            winner_photo_url = None  # Si la foto no es válida, no la mostramos

    return render_template('result.html', winner_name=winner_name, winner_photo=winner_photo_url, total_participants=total_participants)




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