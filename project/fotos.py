"""Fotografías de actividades: subida, galería en vivo y versiones reducidas.

Cada actividad tiene su carpeta en uploads/<actividad>/ y un registro JSON en
database/fotos/ (volumen persistente en Docker) con el hash de cada foto para
detectar duplicados.
"""
import hashlib
import io
import json
import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template, request, send_from_directory, url_for
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge

try:
    import fcntl  # Solo Linux: bloqueo entre workers de Gunicorn
except ImportError:  # Windows (desarrollo)
    fcntl = None

logger = logging.getLogger(__name__)

BASE_DIR = '/app' if os.path.exists('/app') else os.path.dirname(os.path.abspath(__file__))
UPLOAD_BASE = os.path.join(BASE_DIR, 'uploads')
REGISTRY_DIR = os.path.join(BASE_DIR, 'database', 'fotos')

# Para agregar un evento nuevo basta con añadirlo aquí
ACTIVITIES = {
    'cena-gerentes': 'Cena de Gerentes',
    'sesion-gerentes-rrhh': 'Sesión Gerentes RRHH',
    'convivio': 'Convivio 2026',
    'actividad-bananero': 'Actividad del Bananero',
}

MAX_PHOTO_MB = 25
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
# Formato detectado por Pillow -> extensión con la que se guarda
FORMAT_EXTENSIONS = {'JPEG': 'jpg', 'MPO': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}
# Versiones reducidas: miniatura para la galería y vista para el visor
VARIANTS = {'mini': 480, 'vista': 1600}

fotos_bp = Blueprint('fotos', __name__)


# ---------- Utilidades de archivos ----------

def activity_folder(activity):
    folder = os.path.join(UPLOAD_BASE, activity)
    os.makedirs(folder, exist_ok=True)
    return folder


def ensure_activity_folders():
    for activity in ACTIVITIES:
        activity_folder(activity)
    os.makedirs(REGISTRY_DIR, exist_ok=True)


def _allowed_name(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _md5_file(path):
    digest = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


# ---------- Registro de fotos ----------

def _registry_path(activity):
    return os.path.join(REGISTRY_DIR, f'photos_registry_{activity}.json')


@contextmanager
def _registry_lock(activity):
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    with open(_registry_path(activity) + '.lock', 'a') as lock_file:
        if fcntl:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(lock_file, fcntl.LOCK_UN)


def _read_registry(activity):
    path = _registry_path(activity)
    if not os.path.exists(path):
        # Ubicación anterior (directorio de trabajo, no persistente en Docker)
        legacy = f'photos_registry_{activity}.json'
        if not os.path.exists(legacy):
            return []
        path = legacy
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.exception(f"No se pudo leer el registro {path}")
        return []


def _write_registry(activity, registry):
    path = _registry_path(activity)
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as fh:
        json.dump(registry, fh, indent=4, ensure_ascii=False)
    os.replace(tmp_path, path)


def _entry_for_existing_file(activity, filename):
    """Crea la entrada de registro para un archivo que está en disco pero no registrado."""
    path = os.path.join(activity_folder(activity), filename)
    try:
        upload_date = datetime.strptime(filename[:15], '%Y%m%d_%H%M%S').strftime('%Y%m%d_%H%M%S')
    except ValueError:
        upload_date = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y%m%d_%H%M%S')
    return {
        'filename': filename,
        'original_name': filename,
        'upload_date': upload_date,
        'file_hash': _md5_file(path),
        'activity': activity,
    }


def get_photos(activity):
    """Devuelve las fotos de la actividad (más recientes primero), reconciliando el
    registro con lo que realmente existe en disco."""
    folder = activity_folder(activity)
    on_disk = {
        name for name in os.listdir(folder)
        if _allowed_name(name) and os.path.isfile(os.path.join(folder, name))
    }
    with _registry_lock(activity):
        registry = _read_registry(activity)
        photos = [p for p in registry if p.get('filename') in on_disk]
        known = {p['filename'] for p in photos}
        photos.extend(_entry_for_existing_file(activity, name) for name in sorted(on_disk - known))
        if photos != registry or not os.path.exists(_registry_path(activity)):
            _write_registry(activity, photos)
    return sorted(photos, key=lambda p: p['upload_date'], reverse=True)


# ---------- Subida ----------

def _save_upload(activity, file):
    """Valida y guarda una foto. Devuelve (estado, mensaje, entrada_registro)."""
    original_name = (file.filename or 'foto')[:150]
    data = file.read()

    if not data:
        return 'invalida', 'El archivo está vacío', None
    if len(data) > MAX_PHOTO_MB * 1024 * 1024:
        return 'invalida', f'Supera el máximo de {MAX_PHOTO_MB} MB', None

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
            image_format = img.format
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return 'invalida', 'No es una imagen válida', None

    extension = FORMAT_EXTENSIONS.get(image_format)
    if not extension:
        return 'invalida', 'Formato no permitido (usa JPG, PNG o WEBP)', None

    file_hash = hashlib.md5(data).hexdigest()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Nombre único: los celulares suelen enviar siempre "image.jpg"
    filename = f'{timestamp}_{uuid.uuid4().hex[:8]}.{extension}'

    with _registry_lock(activity):
        registry = _read_registry(activity)
        if any(p.get('file_hash') == file_hash for p in registry):
            return 'duplicada', 'Esta foto ya fue subida', None

        with open(os.path.join(activity_folder(activity), filename), 'wb') as fh:
            fh.write(data)

        entry = {
            'filename': filename,
            'original_name': original_name,
            'upload_date': timestamp,
            'file_hash': file_hash,
            'activity': activity,
        }
        registry.append(entry)
        _write_registry(activity, registry)

    # Fuera del bloqueo: generar la miniatura no debe frenar otras subidas
    _ensure_variant(activity, filename, 'mini')
    return 'subida', 'Foto subida', entry


# ---------- Versiones reducidas ----------

def _variant_path(activity, filename, variant):
    name = os.path.splitext(filename)[0] + '.jpg'
    return os.path.join(activity_folder(activity), f'_{variant}', name)


def _ensure_variant(activity, filename, variant):
    """Genera (si no existe) la versión reducida en JPEG. Devuelve su ruta o None."""
    target = _variant_path(activity, filename, variant)
    if os.path.exists(target):
        return target

    source = os.path.join(activity_folder(activity), filename)
    size = VARIANTS[variant]
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with Image.open(source) as img:
            img.draft('RGB', (size, size))  # Decodificación rápida en JPEG grandes
            img = ImageOps.exif_transpose(img)
            img.thumbnail((size, size))
            if img.mode != 'RGB':
                background = Image.new('RGB', img.size, (255, 255, 255))
                img = img.convert('RGBA')
                background.paste(img, mask=img.getchannel('A'))
                img = background
            tmp_path = target + '.tmp'
            img.save(tmp_path, format='JPEG', quality=82, optimize=True, progressive=True)
        os.replace(tmp_path, target)
        return target
    except Exception:
        logger.exception(f"No se pudo generar la versión '{variant}' de {source}")
        return None


def _photo_payload(activity, photo):
    filename = photo['filename']
    return {
        'filename': filename,
        'mini': url_for('fotos.photo_variant', variant='mini', activity=activity, filename=filename),
        'vista': url_for('fotos.photo_variant', variant='vista', activity=activity, filename=filename),
    }


def _wants_json():
    return request.accept_mimetypes.best_match(['text/html', 'application/json']) == 'application/json'


# ---------- Rutas ----------

def activity_page(activity):
    message = None

    if request.method == 'POST':
        files = [f for f in request.files.getlist('photos') if f and f.filename]
        results = []
        for file in files:
            status, text, entry = _save_upload(activity, file)
            results.append({
                'nombre': file.filename,
                'estado': status,
                'mensaje': text,
                'foto': _photo_payload(activity, entry) if entry else None,
            })

        uploaded = sum(r['estado'] == 'subida' for r in results)
        duplicated = sum(r['estado'] == 'duplicada' for r in results)
        invalid = sum(r['estado'] == 'invalida' for r in results)
        logger.info(f"[{activity}] subidas={uploaded} duplicadas={duplicated} invalidas={invalid}")

        if _wants_json():
            return jsonify({'ok': uploaded > 0, 'resultados': results}), (200 if results else 400)

        parts = []
        if uploaded:
            parts.append(f'{uploaded} foto(s) subida(s)')
        if duplicated:
            parts.append(f'{duplicated} ya existían')
        if invalid:
            parts.append(f'{invalid} no válida(s)')
        message = {
            'type': 'success' if uploaded else 'error',
            'text': ', '.join(parts) if parts else 'No se seleccionó ninguna foto',
        }

    photos = [_photo_payload(activity, p) for p in get_photos(activity)]
    return render_template(
        'index.html',
        message=message,
        photos=photos,
        activity=activity,
        activity_title=ACTIVITIES[activity],
        max_photo_mb=MAX_PHOTO_MB,
    )


for _slug in ACTIVITIES:
    fotos_bp.add_url_rule(
        f'/{_slug}', endpoint=_slug, view_func=activity_page,
        methods=['GET', 'POST'], defaults={'activity': _slug},
    )


@fotos_bp.route('/api/fotos/<activity>')
def photos_api(activity):
    """Lista de fotos para refrescar la galería (reemplaza al antiguo SSE, que
    dejaba un worker de Gunicorn ocupado por cada pestaña abierta)."""
    if activity not in ACTIVITIES:
        abort(404)
    photos = [_photo_payload(activity, p) for p in get_photos(activity)]
    response = jsonify({'fotos': photos, 'total': len(photos)})
    response.headers['Cache-Control'] = 'no-store'
    return response


@fotos_bp.route('/fotos/<variant>/<activity>/<filename>')
def photo_variant(variant, activity, filename):
    if variant not in VARIANTS or activity not in ACTIVITIES or not _allowed_name(filename):
        abort(404)
    folder = activity_folder(activity)
    if not os.path.isfile(os.path.join(folder, filename)):
        abort(404)

    target = _ensure_variant(activity, filename, variant)
    if not target:
        # Nunca se entrega el original como respaldo: solo versiones reducidas
        logger.warning('No se pudo generar la versión %s de %s/%s', variant, activity, filename)
        abort(404)
    return send_from_directory(os.path.dirname(target), os.path.basename(target), max_age=31536000)

# Los originales (uploads/<actividad>/) NO se publican: solo se sirven las versiones
# reducidas de arriba. Para obtener un original, copiarlo directamente desde el servidor.


@fotos_bp.app_errorhandler(RequestEntityTooLarge)
def too_large(error):
    if _wants_json():
        return jsonify({'ok': False, 'mensaje': 'El archivo es demasiado grande'}), 413
    return error
