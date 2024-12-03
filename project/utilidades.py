import os
import json
import hashlib
from flask import current_app

PHOTOS_REGISTRY = 'photos_registry.json'

def allowed_file(filename):
    """Verifica si la extensión del archivo está permitida."""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_hash(file):
    """Calcula el hash del contenido del archivo."""
    file_content = file.read()
    file.seek(0)  # Resetear el puntero del archivo
    return hashlib.md5(file_content).hexdigest()

def load_photos_registry(registry_file='photos_registry.json'):
    try:
        with open(registry_file, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_photos_registry(photos_registry, registry_file='photos_registry.json'):
    with open(registry_file, 'w') as f:
        json.dump(photos_registry, f, indent=4)

def is_duplicate(file_hash, registry):
    """Verifica si el archivo ya existe en el registro."""
    return any(photo.get('file_hash') == file_hash for photo in registry)