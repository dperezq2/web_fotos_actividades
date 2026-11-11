"""Login con CUE y contraseña, protección de rutas y comando para crear el SUPERADMIN.

Toda ruta queda protegida por defecto; solo las fotos de actividades, los
archivos estáticos y el propio login son públicos.
"""
import functools
import secrets
from datetime import datetime

import click
from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import execute, query, registrar_bitacora

auth_bp = Blueprint('auth', __name__)

PUBLIC_ENDPOINTS = {'static', 'auth.login'}
PUBLIC_BLUEPRINTS = {'fotos'}
ROLES = ('SUPERADMIN', 'USUARIO')

# Sin caracteres que se confunden al dictarlos (0/O, 1/l/I)
PASSWORD_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'


def generar_password(longitud=10):
    return ''.join(secrets.choice(PASSWORD_ALPHABET) for _ in range(longitud))


def hash_password(password):
    return generate_password_hash(password)


def inicio_url():
    # Pantalla a la que se llega después del login
    return url_for('sorteos.inicio')


def _safe_next(target):
    """Solo permite redirigir a rutas internas (evita redirecciones abiertas)."""
    if target and target.startswith('/') and not target.startswith('//') and '\\' not in target:
        return target
    return None


def superadmin_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user or g.user['rol'] != 'SUPERADMIN':
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@auth_bp.before_app_request
def proteger_rutas():
    g.user = None
    if request.endpoint is None:  # 404: que lo maneje Flask
        return
    if request.endpoint in PUBLIC_ENDPOINTS or request.blueprint in PUBLIC_BLUEPRINTS:
        if request.endpoint == 'auth.login' and session.get('user_id'):
            _cargar_usuario()
        return

    _cargar_usuario()
    if g.user is None:
        if request.accept_mimetypes.best_match(['text/html', 'application/json']) == 'application/json':
            return jsonify({'ok': False, 'mensaje': 'Sesión no iniciada'}), 401
        return redirect(url_for('auth.login', next=request.full_path.rstrip('?')))


def _cargar_usuario():
    user_id = session.get('user_id')
    if not user_id:
        return
    g.user = query(
        'SELECT id, cue, nombre, rol FROM usuarios WHERE id = %s AND activo = 1',
        (user_id,), one=True,
    )
    if g.user is None:  # Usuario desactivado o eliminado: cerrar su sesión
        session.clear()


@auth_bp.app_context_processor
def inyectar_usuario():
    return {'current_user': g.get('user')}


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if g.user:
        return redirect(inicio_url())

    error = None
    cue = ''
    if request.method == 'POST':
        cue = request.form.get('cue', '').strip()
        password = request.form.get('password', '')
        user = query('SELECT id, password_hash, activo FROM usuarios WHERE cue = %s', (cue,), one=True)

        if user and user['activo'] and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            registrar_bitacora('LOGIN', usuario_id=user['id'])
            return redirect(_safe_next(request.args.get('next')) or inicio_url())

        registrar_bitacora('LOGIN_FALLIDO', {'cue': cue[:10]})
        error = 'CUE o contraseña incorrectos'

    return render_template('auth/login.html', error=error, cue=cue, anio=datetime.now().year)


@auth_bp.route('/logout', methods=['POST'])
def logout():
    if g.user:
        registrar_bitacora('LOGOUT')
    session.clear()
    flash('Sesión cerrada', 'success')
    return redirect(url_for('auth.login'))


@click.command('crear-superadmin')
@click.option('--cue', prompt='CUE', help='CUE con el que iniciará sesión')
@click.option('--nombre', prompt='Nombre completo')
@click.password_option('--password', prompt='Contraseña', confirmation_prompt='Repite la contraseña')
def crear_superadmin(cue, nombre, password):
    """Crea un SUPERADMIN o, si el CUE ya existe, lo convierte en SUPERADMIN y cambia su contraseña."""
    cue = cue.strip()
    if not cue or len(cue) > 10:
        raise click.BadParameter('El CUE debe tener entre 1 y 10 caracteres', param_hint='--cue')
    if len(password) < 8:
        raise click.BadParameter('La contraseña debe tener al menos 8 caracteres', param_hint='--password')

    execute(
        '''INSERT INTO usuarios (cue, nombre, password_hash, rol, activo)
           VALUES (%s, %s, %s, 'SUPERADMIN', 1) AS nuevo
           ON DUPLICATE KEY UPDATE nombre = nuevo.nombre, password_hash = nuevo.password_hash,
                                   rol = 'SUPERADMIN', activo = 1''',
        (cue, nombre.strip(), hash_password(password)),
    )
    registrar_bitacora('CREAR_SUPERADMIN_CLI', {'cue': cue})
    click.echo(f'SUPERADMIN {cue} listo. Ya puede iniciar sesión en /login')


def init_app(app):
    app.register_blueprint(auth_bp)
    app.cli.add_command(crear_superadmin)
