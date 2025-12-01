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

# ========== IMPORTAR MODELS PARA BASE DE DATOS ==========
from models import db

app = Flask(__name__)

# Configurar el almacenamiento de sesiones en el servidor
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_FILE_DIR'] = './.flask_session'

app.secret_key = os.urandom(24)
Session(app)

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB máximo


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
            session['participants'] = participants
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
                            'activity': activity
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
    global db  # Declarar global al inicio de la función
    
    if not sorteo_manager.has_file():
        flash('No hay archivo CSV cargado', 'danger')
        return redirect(url_for('upload_file'))
    
    try:
        num_winners = int(request.form.get('num_winners', 1))
        success, result = sorteo_manager.get_winners(num_winners)
        if success:
            session['current_winners'] = result
            
            # ========== GUARDAR EN BASE DE DATOS ==========
            try:
                # Verificar que db esté disponible
                if db is None:
                    logger.error("❌ La instancia de base de datos no está disponible")
                    flash('Error: Base de datos no disponible. Revisa los logs.', 'danger')
                    return redirect(url_for('show_winners'))
                
                # Obtener nombre del archivo original
                original_filename = sorteo_manager.uploaded_file.stem if sorteo_manager.uploaded_file else "sorteo_sin_nombre"
                
                # Contar participantes totales
                total_participants = len(sorteo_manager.df)
                
                logger.info(f"📝 Intentando guardar sorteo: {original_filename}")
                logger.info(f"📊 Participantes: {total_participants}, Ganadores: {num_winners}")
                
                # Verificar que la BD existe y está inicializada
                from pathlib import Path
                db_path = Path('sorteos_historico.db')
                if not db_path.exists():
                    logger.warning("⚠️ BD no existe, inicializando...")
                    from models import init_db
                    db = init_db()
                
                # Guardar sorteo
                sorteo_id = db.guardar_sorteo(
                    nombre_archivo=original_filename,
                    total_participantes=total_participants,
                    num_ganadores=num_winners,
                    descripcion=f"Sorteo realizado el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                )
                
                logger.info(f"✅ Sorteo guardado con ID: {sorteo_id}")
                
                # Guardar ganadores
                db.guardar_ganadores(sorteo_id, result)
                
                logger.info(f"✅ {len(result)} ganadores guardados exitosamente")
                flash(f'Sorteo guardado exitosamente en el historial (ID: {sorteo_id})', 'success')
                
            except Exception as db_error:
                import traceback
                error_detail = traceback.format_exc()
                logger.error(f"❌ Error al guardar en BD: {db_error}")
                logger.error(f"📋 Detalle del error:\n{error_detail}")
                flash(f'Advertencia: No se pudo guardar el sorteo en el historial. Error: {str(db_error)}', 'warning')
            # ========== FIN GUARDADO EN BD ==========
            
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


# ========== NUEVAS RUTAS PARA HISTORIAL DE SORTEOS ==========

@app.route('/historial')
def historial_sorteos():
    """Muestra todos los sorteos realizados"""
    try:
        sorteos = db.obtener_sorteos()
        estadisticas = db.obtener_estadisticas()
        return render_template('historial.html', sorteos=sorteos, estadisticas=estadisticas)
    except Exception as e:
        logger.error(f"Error al cargar historial: {e}")
        flash('Error al cargar el historial de sorteos', 'danger')
        return redirect(url_for('upload_file'))


@app.route('/historial/<int:sorteo_id>')
def detalle_sorteo(sorteo_id):
    """Muestra los ganadores de un sorteo específico"""
    try:
        sorteo = db.obtener_sorteo(sorteo_id)
        if not sorteo:
            flash('Sorteo no encontrado', 'warning')
            return redirect(url_for('historial_sorteos'))
        
        ganadores = db.obtener_ganadores_sorteo(sorteo_id)
        
        # Procesar rutas de fotos
        for ganador in ganadores:
            path = ganador.get('path_fotografia', '').strip()
            if path and path != 'nan':
                ganador['path_fotografia'] = path
            else:
                ganador['path_fotografia'] = ''
        
        return render_template('detalle_sorteo.html', sorteo=sorteo, ganadores=ganadores)
    except Exception as e:
        logger.error(f"Error al cargar detalle de sorteo: {e}")
        flash('Error al cargar el detalle del sorteo', 'danger')
        return redirect(url_for('historial_sorteos'))


@app.route('/historial/eliminar/<int:sorteo_id>', methods=['POST'])
def eliminar_sorteo(sorteo_id):
    """Elimina un sorteo y todos sus ganadores"""
    try:
        if db.eliminar_sorteo(sorteo_id):
            flash('Sorteo eliminado exitosamente', 'success')
            logger.info(f"Sorteo {sorteo_id} eliminado")
        else:
            flash('No se pudo eliminar el sorteo', 'warning')
    except Exception as e:
        logger.error(f"Error al eliminar sorteo: {e}")
        flash('Error al eliminar el sorteo', 'danger')
    
    return redirect(url_for('historial_sorteos'))


@app.route('/verificar_ganador/<cue>')
def verificar_ganador(cue):
    """Verifica si un empleado ya ha ganado anteriormente"""
    try:
        historial = db.verificar_ganador_previo(cue)
        return jsonify({
            'success': True,
            'ha_ganado': len(historial) > 0,
            'veces_ganadas': len(historial),
            'sorteos': historial
        })
    except Exception as e:
        logger.error(f"Error al verificar ganador: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== FIN NUEVAS RUTAS ==========


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

# Configuración para Docker - detectar si estamos en contenedor
if os.path.exists('/app'):
    # Estamos en Docker
    BASE_DIR = '/app'
else:
    # Estamos en desarrollo
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configurar paths absolutos
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['SESSION_FILE_DIR'] = os.path.join(BASE_DIR, '.flask_session')

# Asegurar que los directorios existen
def ensure_directories():
    directories = [
        app.config['UPLOAD_FOLDER'],
        os.path.join(app.config['UPLOAD_FOLDER'], 'cena-gerentes'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'sesion-gerentes-rrhh'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'convivio'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'actividad-bananero'),
        os.path.join(BASE_DIR, 'static', 'img'),
        app.config['SESSION_FILE_DIR'],
        os.path.join(BASE_DIR, 'database'),
        os.path.join(BASE_DIR, 'logs')
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True, mode=0o755)
        print(f"✅ Directorio creado/verificado: {directory}")

# Llamar al inicio
ensure_directories()

# Configuración para proxy reverso
class ReverseProxied(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        scheme = environ.get('HTTP_X_FORWARDED_PROTO', '')
        if scheme:
            environ['wsgi.url_scheme'] = scheme
        return self.app(environ, start_response)

app.wsgi_app = ReverseProxied(app.wsgi_app)


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