"""Conexión a MySQL: una conexión por petición, guardada en flask.g."""
import json
import logging
import os
from contextlib import contextmanager

import pymysql
from flask import g, has_request_context, request


def _config():
    return {
        'host': os.environ.get('MYSQL_HOST', '127.0.0.1'),
        'port': int(os.environ.get('MYSQL_PORT', 3306)),
        'user': os.environ.get('MYSQL_USER', 'sorteos_app'),
        'password': os.environ.get('MYSQL_PASSWORD', ''),
        'database': os.environ.get('MYSQL_DATABASE', 'sorteos_pb'),
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor,
        'autocommit': False,
        'connect_timeout': 5,
        # Cada consulta ve lo último confirmado por otros (p. ej. ganadores recién sorteados)
        'init_command': 'SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED',
    }


def get_db():
    if 'db' not in g:
        g.db = pymysql.connect(**_config())
    return g.db


def close_db(exception=None):
    conn = g.pop('db', None)
    if conn is not None:
        try:
            conn.rollback()  # Descarta lo que no se confirmó explícitamente
        finally:
            conn.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def query(sql, params=None, one=False):
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone() if one else cur.fetchall()


@contextmanager
def transaction():
    """Agrupa varias escrituras: confirma al final o revierte todo si algo falla."""
    conn = get_db()
    conn.begin()  # Empieza limpia: descarta cualquier lectura previa de la petición
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def execute(sql, params=None):
    with transaction() as cur:
        cur.execute(sql, params)
        return cur.lastrowid


LISTA_POR_DEFECTO = 'Empleados'
LISTA_MAX = 60


def listas_participantes():
    """Listas existentes con sus conteos: [{'lista', 'total', 'elegibles'}], ordenadas por nombre."""
    return query(
        '''SELECT e.lista, COUNT(*) AS total, COALESCE(SUM(e.activo = 1 AND g.id IS NULL), 0) AS elegibles
           FROM empleados e LEFT JOIN ganadores g ON g.empleado_id = e.id
           GROUP BY e.lista ORDER BY e.lista''')


def normalizar_lista(nombre, existentes=None):
    """Limpia el nombre escrito y, si ya existe una lista igual (sin importar mayúsculas
    ni tildes), usa la escritura existente. Devuelve '' si queda vacío."""
    nombre = ' '.join((nombre or '').split())[:LISTA_MAX]
    if existentes is None:
        existentes = [l['lista'] for l in listas_participantes()]
    clave = _clave(nombre)
    return next((l for l in existentes if _clave(l) == clave), nombre)


def _clave(texto):
    import unicodedata
    sin_tildes = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return sin_tildes.casefold()


def registrar_bitacora(accion, detalle=None, usuario_id=None):
    if usuario_id is None and 'user' in g and g.user:
        usuario_id = g.user['id']
    ip = None
    if has_request_context():
        ip = request.headers.get('X-Real-IP') or request.remote_addr
    execute(
        'INSERT INTO bitacora (usuario_id, accion, detalle, ip) VALUES (%s, %s, %s, %s)',
        (usuario_id, accion, json.dumps(detalle, ensure_ascii=False) if detalle else None, ip),
    )


# Cambios de esquema para bases ya creadas (01_schema.sql solo corre en una base nueva).
# Cada uno: (nombre, consulta que devuelve n > 0 si ya está aplicado, sentencias).
# Se aplican al arrancar, en orden, solo si hacen falta.
_EXISTE_COLUMNA = '''SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{}' AND COLUMN_NAME = '{}' '''
_EXISTE_INDICE = '''SELECT COUNT(*) AS n FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{}' AND INDEX_NAME = '{}' '''

VISTA_ELEGIBLES = '''CREATE OR REPLACE VIEW v_empleados_elegibles AS
    SELECT e.* FROM empleados e
    LEFT JOIN ganadores g ON g.empleado_id = e.id
    WHERE e.activo = 1 AND g.id IS NULL'''

MIGRACIONES = [
    ('ganadores.revelado_at', _EXISTE_COLUMNA.format('ganadores', 'revelado_at'),
     ['ALTER TABLE ganadores ADD COLUMN revelado_at DATETIME NULL AFTER fecha']),

    # Listas de participantes ("Empleados", "Cooperativa"...): el mismo CUE puede estar en
    # varias listas, y quien gana en una sigue participando en las demás.
    ('empleados.lista', _EXISTE_COLUMNA.format('empleados', 'lista'),
     ["ALTER TABLE empleados ADD COLUMN lista VARCHAR(60) NOT NULL DEFAULT 'Empleados' AFTER id"]),
    ('empleados: CUE único por lista', _EXISTE_INDICE.format('empleados', 'uq_empleados_lista_cue'),
     ['''ALTER TABLE empleados
            DROP INDEX uq_empleados_cue,
            ADD UNIQUE KEY uq_empleados_lista_cue (lista, cue),
            DROP INDEX idx_empleados_filtros,
            ADD KEY idx_empleados_filtros (lista, empresa, distrito, departamento)''']),
    # La vista guarda las columnas de empleados de cuando se creó: hay que recrearla
    ('v_empleados_elegibles.lista', _EXISTE_COLUMNA.format('v_empleados_elegibles', 'lista'),
     [VISTA_ELEGIBLES]),
    ('sorteos.lista', _EXISTE_COLUMNA.format('sorteos', 'lista'),
     ['ALTER TABLE sorteos ADD COLUMN lista VARCHAR(60) NULL AFTER descripcion',
      "UPDATE sorteos SET lista = 'Empleados' WHERE lista IS NULL"]),  # Los anteriores eran de la única lista
]


def aplicar_migraciones():
    logger = logging.getLogger(__name__)
    try:
        conn = pymysql.connect(**_config())
    except Exception as error:  # La app debe arrancar aunque MySQL falle; se verá en el log
        logger.error(f'No se pudieron revisar las migraciones (sin conexión a MySQL): {error!r}')
        return
    try:
        with conn.cursor() as cur:
            # Los workers de Gunicorn arrancan a la vez: solo uno migra, los demás esperan
            cur.execute("SELECT GET_LOCK('sorteos_migraciones', 60) AS ok")
            if not cur.fetchone()['ok']:
                logger.error('No se pudo obtener el bloqueo para revisar las migraciones')
                return
            try:
                for nombre, verificacion, sentencias in MIGRACIONES:
                    cur.execute(verificacion)
                    if cur.fetchone()['n']:
                        continue
                    for sentencia in sentencias:
                        cur.execute(sentencia)
                    conn.commit()
                    logger.info(f'Migración aplicada: {nombre}')
            finally:
                cur.execute("SELECT RELEASE_LOCK('sorteos_migraciones')")
    except Exception as error:
        logger.error(f'Error al aplicar migraciones: {error!r}')
    finally:
        conn.close()
