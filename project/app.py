"""Actividades Palo Blanco: fotos de eventos (público) y sorteos (con login)."""
import logging
import os

from dotenv import load_dotenv

load_dotenv()  # Variables de .env (MySQL, SECRET_KEY) en desarrollo

from flask import Flask, jsonify, render_template, request
from flask_session import Session
from werkzeug.middleware.proxy_fix import ProxyFix

import auth
import db
from admin import admin_bp
from fotos import ensure_activity_folders, fotos_bp
from sorteos import sorteos_bp

BASE_DIR = '/app' if os.path.exists('/app') else os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
SESSION_DIR = os.path.join(BASE_DIR, '.flask_session')

for directory in (os.path.join(BASE_DIR, 'database'), LOGS_DIR, SESSION_DIR):
    os.makedirs(directory, exist_ok=True)
ensure_activity_folders()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(LOGS_DIR, 'app.log'), encoding='utf-8')],
)


def _load_secret_key():
    """La clave debe ser la misma en todos los workers y sobrevivir reinicios,
    o las sesiones (login) se pierden. Se toma de SECRET_KEY o de un archivo persistente."""
    if os.environ.get('SECRET_KEY'):
        return os.environ['SECRET_KEY']
    key_path = os.path.join(BASE_DIR, 'database', '.secret_key')
    try:
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as fh:
            fh.write(os.urandom(32).hex())
    except FileExistsError:
        pass
    with open(key_path) as fh:
        return fh.read().strip()


app = Flask(__name__)
app.secret_key = _load_secret_key()
app.config.update(
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # Igual que client_max_body_size de Nginx
    SESSION_TYPE='filesystem',
    SESSION_PERMANENT=False,
    SESSION_USE_SIGNER=True,
    SESSION_FILE_DIR=SESSION_DIR,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',  # Bloquea el envío de la sesión en POST desde otros sitios
    SESSION_COOKIE_SECURE=os.environ.get('FLASK_ENV') == 'production',
)
Session(app)

# Nginx informa el esquema (https) y la IP real del cliente
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

db.init_app(app)
db.aplicar_migraciones()
auth.init_app(app)
app.register_blueprint(fotos_bp)
app.register_blueprint(sorteos_bp)
app.register_blueprint(admin_bp)

# Logos de las empresas, en orden. Se muestran con templates/_logos.html en
# fotos, login y ruleta: para agregar o quitar uno basta con editar esta lista.
app.jinja_env.globals['LOGOS'] = [
    ('logo_PB.jpg', 'Palo Blanco'),
    ('logo_banamar.png', 'Banamar'),
    ('logo_highland.png', 'Highland'),
    ('logo_COPEPRIMA.png', 'COPEPRIMA'),
    ('logo_finetropicalfoods.png', 'Fine Tropical Foods'),
    ('logo_agropecuariaprimavera.png', 'Agropecuaria Primavera'),
]


ERRORES = {
    403: ('Acceso restringido', 'No tienes permiso para ver esta página.'),
    404: ('Página no encontrada', 'La dirección no existe o fue eliminada.'),
    500: ('Algo salió mal', 'Ocurrió un error inesperado. Intenta de nuevo en unos momentos.'),
}


def _pagina_error(codigo):
    titulo, mensaje = ERRORES[codigo]
    if request.accept_mimetypes.best_match(['text/html', 'application/json']) == 'application/json':
        return jsonify({'ok': False, 'mensaje': mensaje}), codigo
    return render_template('error.html', codigo=codigo, titulo=titulo, mensaje=mensaje), codigo


for _codigo in ERRORES:
    app.register_error_handler(_codigo, lambda e, c=_codigo: _pagina_error(c))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
