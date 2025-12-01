from flask import Flask, request, send_from_directory, render_template, jsonify, Response, url_for, redirect, session, flash
from utils.sorter import SorteoManager
from pathlib import Path
from flask_session import Session
import time
import os
from datetime import datetime
import json
from werkzeug.utils import secure_filename
import requests
import logging
import pandas as pd

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

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB máximo


# NUEVO: Proxy de imágenes
# @app.route('/image-proxy')
#def proxy_image():
    # Obtener la URL de la imagen desde los parámetros de la solicitud
 #   image_url = request.args.get('url')
    
  #  try:
        # Descargar la imagen
   #     response = requests.get(image_url, timeout=10)
        
        # Verificar que la descarga fue exitosa
    #    if response.status_code == 200:
            # Devolver la imagen con el tipo MIME correcto
     #       return Response(response.content, mimetype=response.headers.get('content-type', 'image/jpeg'))
      #  else:
            # Si la descarga falla, devolver una imagen por defecto o un error
       #     return Response('Error al cargar la imagen', status=404)
    
   # except requests.RequestException:
        # Manejar errores de solicitud (timeout, conexión, etc.)
    #    return Response('Error al descargar la imagen', status=500)


@app.route('/sorteo', methods=['GET', 'POST'])
def index():
    # Clear previous session data when starting a new raffle
    session.clear()

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
            
            # Store the original filename without extension
            original_filename = os.path.splitext(filename)[0]

            # Guardar el ganador y otros datos en la sesión
            session['winner'] = winner
            session['total_participants'] = len(participants)
            session['participants'] = participants  # Guardamos la lista de participantes
            session['original_filename'] = original_filename

            # Redirigir a la página de resultados
            return redirect(url_for('result'))
    
    return render_template('index_sorteo.html')


@app.route('/result', methods=['GET', 'POST'])
def result():
    winner = session.get('winner')
    participants = session.get('participants', [])
    total_participants = session.get('total_participants', 0)
    original_filename = session.get('original_filename', 'ganador')
    previous_winners = session.get('previous_winners', [])
    winner_count = len(previous_winners) + 1

    if not winner or not total_participants:
        return redirect(url_for('index'))

    if request.method == 'POST':
        if participants:
            # Exclude the previous winner from participants
            participants = [p for p in participants if p['CUE'] != winner['CUE']]
            
            # Update total participants
            total_participants = len(participants)
            
            # Perform a new raffle
            winner = perform_raffle(participants)
            
            # Update session variables
            session['winner'] = winner
            session['participants'] = participants
            session['total_participants'] = total_participants

            # Track previous winners
            previous_winners.insert(0, winner)
            session['previous_winners'] = previous_winners[:5]

            return redirect(url_for('result'))

    # Prepare winner information
    winner_name = winner.get('Empleado', 'No disponible')
    winner_photo_url = winner.get('PathFotografia', '')

    # Validate and proxy the winner's photo
    if winner_photo_url:
        is_valid_photo = validate_photo_path(winner_photo_url)
        if is_valid_photo:
            winner_photo_url = url_for('proxy_image', url=winner_photo_url)
        else:
            winner_photo_url = None

    return render_template('result.html', 
                            winner=winner, 
                            winner_name=winner_name, 
                            winner_photo=winner_photo_url, 
                            total_participants=total_participants, 
                            original_filename=original_filename,
                            winner_count=winner_count)




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

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('sorteo_app.log')
    ]
)
logger = logging.getLogger(__name__)

# Crear carpeta de uploads si no existe
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)

# Asegurar que existe la carpeta de imágenes estáticas
Path('static/img').mkdir(parents=True, exist_ok=True)

# Instancia del manejador de sorteos
sorteo_manager = SorteoManager()

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # Verificar si se subió un archivo
        if 'file' not in request.files:
            flash('No se seleccionó ningún archivo', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No se seleccionó ningún archivo', 'danger')
            return redirect(request.url)
        
        # Aceptar archivos .csv
        if file and (file.filename.lower().endswith('.csv')):
            filename = secure_filename(file.filename)
            file_path = Path(app.config['UPLOAD_FOLDER']) / filename
            file.save(file_path)
            
            logger.info(f"Archivo guardado en: {file_path}")
            
            # Intento de análisis preliminar para diagnóstico
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    preview = f.read(1000)  # Leer los primeros 1000 caracteres
                logger.info(f"Vista previa del archivo:\n{preview}")
            except Exception as e:
                logger.warning(f"No se pudo leer vista previa: {e}")
            
            # Cargar el archivo en el manager
            success, message = sorteo_manager.load_csv(file_path)
            if success:
                flash(message, 'success')
                return redirect(url_for('select_winners'))
            else:
                flash(message, 'danger')
                
                # Añadir información de debug para ayudar al usuario
                try:
                    debug_info = "Información de diagnóstico del archivo CSV:\n"
                    
                    # Intentar leer con pandas y mostrar las columnas
                    try:
                        df = pd.read_csv(file_path, nrows=5, encoding='utf-8', on_bad_lines='skip')
                        column_info = f"Columnas detectadas por pandas: {', '.join(df.columns.tolist())}"
                        flash(column_info, 'info')
                        logger.info(column_info)
                    except Exception as e:
                        logger.warning(f"Error en lectura diagnóstica: {e}")
                    
                    # Si hay un método de diagnóstico en SorteoManager, usarlo
                    if hasattr(sorteo_manager, 'get_sample_data'):
                        sample_data = sorteo_manager.get_sample_data()
                        logger.info(f"Muestra de datos:\n{sample_data}")
                except Exception as debug_error:
                    logger.error(f"Error en diagnóstico: {debug_error}")
                
                return redirect(request.url)
        
        flash('Por favor, sube un archivo CSV válido', 'danger')
    
    return render_template('upload.html')

@app.route('/view_csv_structure')
def view_csv_structure():
    """Página de diagnóstico para ver la estructura del CSV cargado"""
    if not sorteo_manager.has_file():
        flash('No hay archivo CSV cargado', 'warning')
        return redirect(url_for('upload_file'))
    
    try:
        csv_structure = {
            'columns': sorteo_manager.df.columns.tolist(),
            'sample': sorteo_manager.df.head(5).to_dict('records')
        }
        return render_template('debug_csv.html', csv_structure=csv_structure)
    except Exception as e:
        flash(f'Error al analizar estructura: {str(e)}', 'danger')
        return redirect(url_for('upload_file'))

@app.route('/select_winners', methods=['GET', 'POST'])
def select_winners():
    if not sorteo_manager.has_file():
        flash('Primero debes subir un archivo CSV', 'danger')
        return redirect(url_for('upload_file'))
    
    if request.method == 'POST':
        try:
            num_winners = int(request.form.get('num_winners', 1))
            if num_winners < 1:
                flash('El número de ganadores debe ser mayor que 0', 'danger')
                return redirect(request.url)

            # Verificar si hay suficientes disponibles (sin hacer aún el sorteo)
            previous_winner_cues = [w['CUE'] for w in sorteo_manager.winners] if sorteo_manager.winners else []
            available = sorteo_manager.df if not previous_winner_cues else sorteo_manager.df[~sorteo_manager.df['CUE'].isin(previous_winner_cues)]
            if len(available) < num_winners:
                flash(f'No hay suficientes empleados disponibles ({len(available)} restantes)', 'danger')
                return redirect(request.url)
            
            # Guardar número de ganadores en sesión
            session['pending_num_winners'] = num_winners
            return redirect(url_for('loading_page'))  # Mostrar animación

        except ValueError:
            flash('Por favor, ingresa un número válido', 'danger')

    return render_template('upload.html', has_file=True)

@app.route('/upload', methods=['GET'])
def go_to_upload():
    return redirect(url_for('upload_file'))



@app.route('/winners')
def show_winners():
    winners = session.get('current_winners', [])
    if not winners:
        flash('No hay ganadores seleccionados', 'warning')
        return redirect(url_for('select_winners'))
    
    # Asegurarse de que todos los ganadores tengan la ruta de la foto en el formato correcto
    for winner in winners:
        if 'PathFotografia' in winner:
            # Limpiar la ruta
            path = winner['PathFotografia'].strip()
            # Eliminar cualquier 'nan' o texto vacío
            if path == 'nan' or not path:
                winner['PathFotografia'] = ''
            else:
                winner['PathFotografia'] = path
                logger.info(f"Ruta de foto para {winner.get('Empleado', 'Unknown')}: {path}")
    
    return render_template('winners.html', winners=winners)


@app.route('/finalize_winner_selection', methods=['POST'])
def finalize_winner_selection():
    if not sorteo_manager.has_file():
        flash('No hay archivo CSV cargado', 'danger')
        return redirect(url_for('upload_file'))
    
    try:
        num_winners = int(request.form.get('num_winners', 1))
        success, result = sorteo_manager.get_winners(num_winners)
        if success:
            session['current_winners'] = result
            return redirect(url_for('show_winners'))
        else:
            flash(result, 'danger')
            return redirect(url_for('select_winners'))
    except Exception as e:
        flash(f'Error inesperado: {e}', 'danger')
        return redirect(url_for('select_winners'))


@app.route('/reset')
def reset_sorteo():
    success, message = sorteo_manager.reset_sorteo()
    flash(message, 'success')
    return redirect(url_for('select_winners'))

@app.route('/reset_sorteo', methods=['POST'])
def reset_sorteo_principal():
    sorteo_manager.df = None
    sorteo_manager.winners = []
    sorteo_manager.uploaded_file = None
    flash("El sorteo fue anulado. Puedes subir un nuevo archivo CSV.", "info")
    return redirect(url_for('upload_file'))


@app.route('/proxy_image/<path:image_url>')
def proxy_image(image_url):
    try:
        if not image_url or image_url.strip() == '' or image_url.strip().lower() == 'nan':
            logger.warning("URL de imagen vacía o 'nan'")
            return redirect(url_for('static', filename='img/placeholder.png'))

        image_url = image_url.strip()
        logger.info(f"Solicitando imagen: {image_url}")

        # Si ya es una URL completa, úsala directamente
        if image_url.startswith('http'):
            full_url = image_url
        else:
            full_url = f"{app.config['IMAGE_SERVER'].rstrip('/')}/{image_url.lstrip('/')}"

        logger.info(f"URL completa: {full_url}")

        response = requests.get(full_url, stream=True, timeout=5)
        if response.status_code == 200:
            logger.info(f"Imagen encontrada: {image_url}")
            return Response(
                response.content,
                mimetype=response.headers.get('Content-Type', 'image/jpeg'),
                status=response.status_code
            )
        else:
            logger.warning(f"Imagen no encontrada (status {response.status_code}): {image_url}")
            return redirect(url_for('static', filename='img/placeholder.png'))
    except Exception as e:
        logger.error(f"Error al obtener imagen: {e}")
        return redirect(url_for('static', filename='img/placeholder.png'))


@app.route('/debug_info')
def debug_info():
    """Página de diagnóstico para desarrolladores"""
    info = {
        'app_config': {k: v for k, v in app.config.items() if k not in ['SECRET_KEY']},
        'has_file': sorteo_manager.has_file(),
        'winners_count': len(sorteo_manager.winners) if sorteo_manager.winners else 0
    }
    
    if sorteo_manager.has_file():
        info['csv_columns'] = sorteo_manager.df.columns.tolist()
        info['csv_rows'] = len(sorteo_manager.df)
    
    return render_template('debug_info.html', info=info)

@app.route('/loading')
def loading_page():
    num_winners = session.get('pending_num_winners')
    if not num_winners:
        flash('Número de ganadores no especificado', 'danger')
        return redirect(url_for('select_winners'))
    
    return render_template('loading.html', num_winners=num_winners)

if __name__ == '__main__':
    # Verificar que existe la imagen placeholder
    placeholder_path = Path('static/img/placeholder.png')
    if not placeholder_path.exists():
        logger.warning("No se encuentra la imagen placeholder. Creando una...")
        # Crear un placeholder básico
        try:
            import urllib.request
            urllib.request.urlretrieve(
                "https://via.placeholder.com/150?text=Sin+Foto",
                placeholder_path
            )
        except:
            # Si no se puede descargar, crear un archivo vacío
            placeholder_path.touch()
            logger.error("No se pudo crear la imagen placeholder")
    
    app.run(host='0.0.0.0', port=3000, debug=True)