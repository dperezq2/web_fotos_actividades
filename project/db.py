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
# Cada uno: (tabla, columna, sentencia). Se aplican al arrancar si la columna no existe.
MIGRACIONES = [
    ('ganadores', 'revelado_at',
     'ALTER TABLE ganadores ADD COLUMN revelado_at DATETIME NULL AFTER fecha'),
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
            for tabla, columna, sentencia in MIGRACIONES:
                cur.execute(
                    '''SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s''',
                    (tabla, columna))
                if cur.fetchone()['n']:
                    continue
                try:
                    cur.execute(sentencia)
                    logger.info(f'Migración aplicada: {tabla}.{columna}')
                except pymysql.err.OperationalError as error:
                    if error.args[0] != 1060:  # Otro worker ya la aplicó (columna duplicada)
                        raise
        conn.commit()
    finally:
        conn.close()
