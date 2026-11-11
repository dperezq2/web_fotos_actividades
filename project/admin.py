"""Administración (solo SUPERADMIN): usuarios del sistema y personal participante."""
import csv
import io
import re

from flask import Blueprint, Response, flash, g, redirect, render_template, request, session, url_for

from auth import ROLES, generar_password, hash_password, superadmin_required
from db import execute, query, registrar_bitacora, transaction

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

CUE_PATTERN = re.compile(r'^[0-9A-Za-z-]{1,10}$')


@admin_bp.before_request
@superadmin_required
def solo_superadmin():
    pass


# ==================== Usuarios ====================

@admin_bp.route('/usuarios')
def usuarios():
    lista = query('SELECT id, cue, nombre, rol, activo, created_at FROM usuarios ORDER BY activo DESC, nombre')
    # La contraseña generada se muestra una sola vez
    password_generada = session.pop('password_generada', None)
    return render_template('admin/usuarios.html', usuarios=lista, roles=ROLES,
                           password_generada=password_generada)


@admin_bp.route('/usuarios', methods=['POST'])
def crear_usuario():
    cue = request.form.get('cue', '').strip()
    nombre = request.form.get('nombre', '').strip()
    rol = request.form.get('rol', 'USUARIO')

    if not CUE_PATTERN.match(cue):
        flash('El CUE debe tener de 1 a 10 caracteres (números o letras)', 'error')
    elif not nombre or len(nombre) > 150:
        flash('Escribe el nombre del usuario', 'error')
    elif rol not in ROLES:
        flash('Rol no válido', 'error')
    elif query('SELECT id FROM usuarios WHERE cue = %s', (cue,), one=True):
        flash(f'Ya existe un usuario con el CUE {cue}', 'error')
    else:
        password = generar_password()
        execute(
            'INSERT INTO usuarios (cue, nombre, password_hash, rol) VALUES (%s, %s, %s, %s)',
            (cue, nombre, hash_password(password), rol),
        )
        registrar_bitacora('CREAR_USUARIO', {'cue': cue, 'rol': rol})
        session['password_generada'] = {'cue': cue, 'nombre': nombre, 'password': password, 'nuevo': True}
    return redirect(url_for('admin.usuarios'))


def _usuario_editable(user_id):
    """Devuelve el usuario si existe y no es el usuario actual (no puede modificarse a sí mismo)."""
    usuario = query('SELECT id, cue, nombre, rol, activo FROM usuarios WHERE id = %s', (user_id,), one=True)
    if not usuario:
        flash('Usuario no encontrado', 'error')
        return None
    if usuario['id'] == g.user['id']:
        flash('No puedes modificar tu propio usuario desde aquí', 'error')
        return None
    return usuario


@admin_bp.route('/usuarios/<int:user_id>/password', methods=['POST'])
def regenerar_password(user_id):
    usuario = _usuario_editable(user_id)
    if usuario:
        password = generar_password()
        execute('UPDATE usuarios SET password_hash = %s WHERE id = %s', (hash_password(password), user_id))
        registrar_bitacora('REGENERAR_PASSWORD', {'cue': usuario['cue']})
        session['password_generada'] = {'cue': usuario['cue'], 'nombre': usuario['nombre'],
                                        'password': password, 'nuevo': False}
    return redirect(url_for('admin.usuarios'))


@admin_bp.route('/usuarios/<int:user_id>/estado', methods=['POST'])
def cambiar_estado_usuario(user_id):
    usuario = _usuario_editable(user_id)
    if usuario:
        nuevo = 0 if usuario['activo'] else 1
        execute('UPDATE usuarios SET activo = %s WHERE id = %s', (nuevo, user_id))
        registrar_bitacora('ACTIVAR_USUARIO' if nuevo else 'DESACTIVAR_USUARIO', {'cue': usuario['cue']})
        flash(f"{usuario['nombre']} {'activado' if nuevo else 'desactivado'}", 'success')
    return redirect(url_for('admin.usuarios'))


@admin_bp.route('/usuarios/<int:user_id>/rol', methods=['POST'])
def cambiar_rol(user_id):
    usuario = _usuario_editable(user_id)
    if usuario:
        nuevo = 'USUARIO' if usuario['rol'] == 'SUPERADMIN' else 'SUPERADMIN'
        execute('UPDATE usuarios SET rol = %s WHERE id = %s', (nuevo, user_id))
        registrar_bitacora('CAMBIAR_ROL', {'cue': usuario['cue'], 'rol': nuevo})
        flash(f"{usuario['nombre']} ahora es {nuevo}", 'success')
    return redirect(url_for('admin.usuarios'))


# ==================== Empleados ====================

CSV_COLUMNS = ('cue', 'nombre_completo', 'empresa', 'distrito', 'departamento', 'path_fotografia')
CSV_REQUIRED = ('cue', 'nombre_completo')
CSV_MAX_LENGTH = {'cue': 10, 'nombre_completo': 150, 'empresa': 60, 'distrito': 60,
                  'departamento': 80, 'path_fotografia': 255}
CSV_MAX_BYTES = 5 * 1024 * 1024
MAX_ERRORES_MOSTRADOS = 25
POR_PAGINA = 50


@admin_bp.route('/empleados')
def empleados():
    q = request.args.get('q', '').strip()
    empresa = request.args.get('empresa', '')
    distrito = request.args.get('distrito', '')
    pagina = max(request.args.get('pagina', 1, type=int), 1)

    condiciones, params = [], []
    if q:
        condiciones.append('(e.cue LIKE %s OR e.nombre_completo LIKE %s OR e.departamento LIKE %s)')
        params += [f'%{q}%'] * 3
    if empresa:
        condiciones.append('e.empresa = %s')
        params.append(empresa)
    if distrito:
        condiciones.append('e.distrito = %s')
        params.append(distrito)
    where = ('WHERE ' + ' AND '.join(condiciones)) if condiciones else ''

    total_filtrado = query(f'SELECT COUNT(*) AS n FROM empleados e {where}', params, one=True)['n']
    lista = query(
        f'''SELECT e.*, (g.id IS NOT NULL) AS ha_ganado
            FROM empleados e LEFT JOIN ganadores g ON g.empleado_id = e.id
            {where}
            ORDER BY e.nombre_completo
            LIMIT %s OFFSET %s''',
        params + [POR_PAGINA, (pagina - 1) * POR_PAGINA],
    )

    resumen = query(
        '''SELECT COUNT(*) AS total,
                  COALESCE(SUM(e.activo = 1), 0) AS activos,
                  COUNT(g.id) AS ganadores,
                  COALESCE(SUM(e.activo = 1 AND g.id IS NULL), 0) AS elegibles
           FROM empleados e LEFT JOIN ganadores g ON g.empleado_id = e.id''',
        one=True,
    )
    empresas = [r['empresa'] for r in query(
        'SELECT DISTINCT empresa FROM empleados WHERE empresa IS NOT NULL ORDER BY empresa')]
    distritos = [r['distrito'] for r in query(
        'SELECT DISTINCT distrito FROM empleados WHERE distrito IS NOT NULL ORDER BY distrito')]

    return render_template(
        'admin/empleados.html',
        empleados=lista, resumen=resumen, empresas=empresas, distritos=distritos,
        q=q, empresa=empresa, distrito=distrito, pagina=pagina,
        total_paginas=max((total_filtrado + POR_PAGINA - 1) // POR_PAGINA, 1),
        total_filtrado=total_filtrado,
        resultado_importacion=session.pop('resultado_importacion', None),
    )


@admin_bp.route('/empleados/<int:empleado_id>/estado', methods=['POST'])
def cambiar_estado_empleado(empleado_id):
    empleado = query('SELECT id, cue, nombre_completo, activo FROM empleados WHERE id = %s',
                     (empleado_id,), one=True)
    if empleado:
        nuevo = 0 if empleado['activo'] else 1
        execute('UPDATE empleados SET activo = %s WHERE id = %s', (nuevo, empleado_id))
        registrar_bitacora('ACTIVAR_EMPLEADO' if nuevo else 'DESACTIVAR_EMPLEADO', {'cue': empleado['cue']})
        flash(f"{empleado['nombre_completo']} {'participará' if nuevo else 'ya no participará'} en los sorteos",
              'success')
    return redirect(request.referrer or url_for('admin.empleados'))


@admin_bp.route('/empleados/plantilla.csv')
def plantilla_csv():
    contenido = ','.join(CSV_COLUMNS) + '\r\n' + '24702,Sergio Israel Monteflores Mujo,Palo Blanco,Distrito 1,SISTEMAS,\r\n'
    return Response(
        '﻿' + contenido,  # BOM para que Excel respete los acentos
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=plantilla_empleados.csv'},
    )


def _decodificar(raw):
    for encoding in ('utf-8-sig', 'cp1252'):  # Excel en Windows suele guardar en cp1252
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def leer_csv_empleados(raw):
    """Valida el CSV completo. Devuelve (filas, errores); si hay errores no se importa nada."""
    texto = _decodificar(raw)
    # Excel en español guarda con ";" en lugar de ","
    primera_linea = texto.split('\n', 1)[0]
    separador = max((',', ';', '\t'), key=primera_linea.count)

    reader = csv.reader(io.StringIO(texto), delimiter=separador)
    encabezados = next(reader, None)
    if not encabezados:
        return [], ['El archivo está vacío']

    encabezados = [h.strip().lower().replace(' ', '_') for h in encabezados]
    faltantes = [c for c in CSV_REQUIRED if c not in encabezados]
    if faltantes:
        return [], [f"Faltan las columnas: {', '.join(faltantes)}. Encabezados encontrados: {', '.join(encabezados)}"]

    indices = {col: encabezados.index(col) for col in CSV_COLUMNS if col in encabezados}
    filas, errores, vistos = [], [], {}

    for numero, valores in enumerate(reader, start=2):
        if not any(v.strip() for v in valores):
            continue  # Línea en blanco
        fila = {}
        for col in CSV_COLUMNS:
            idx = indices.get(col)
            valor = valores[idx].strip() if idx is not None and idx < len(valores) else ''
            fila[col] = valor or None

        problemas = []
        if not fila['cue']:
            problemas.append('CUE vacío')
        elif not CUE_PATTERN.match(fila['cue']):
            problemas.append(f"CUE no válido ({fila['cue']})")
        elif fila['cue'] in vistos:
            problemas.append(f"CUE {fila['cue']} repetido (también en la línea {vistos[fila['cue']]})")
        if not fila['nombre_completo']:
            problemas.append('nombre vacío')
        for col, maximo in CSV_MAX_LENGTH.items():
            if fila[col] and len(fila[col]) > maximo:
                problemas.append(f'{col} supera {maximo} caracteres')

        if problemas:
            errores.append(f"Línea {numero}: {'; '.join(problemas)}")
        else:
            vistos[fila['cue']] = numero
            filas.append(fila)

    if not filas and not errores:
        errores.append('El archivo no tiene empleados')
    return filas, errores


@admin_bp.route('/empleados/importar', methods=['POST'])
def importar_empleados():
    archivo = request.files.get('archivo')
    desactivar_faltantes = request.form.get('desactivar_faltantes') == '1'

    if not archivo or not archivo.filename:
        flash('Selecciona un archivo CSV', 'error')
        return redirect(url_for('admin.empleados'))

    raw = archivo.read(CSV_MAX_BYTES + 1)
    if len(raw) > CSV_MAX_BYTES:
        flash('El archivo supera 5 MB', 'error')
        return redirect(url_for('admin.empleados'))

    filas, errores = leer_csv_empleados(raw)
    if errores:
        session['resultado_importacion'] = {
            'ok': False,
            'archivo': archivo.filename,
            'errores': errores[:MAX_ERRORES_MOSTRADOS],
            'total_errores': len(errores),
        }
        return redirect(url_for('admin.empleados'))

    existentes = {r['cue'] for r in query('SELECT cue FROM empleados')}
    nuevos = sum(f['cue'] not in existentes for f in filas)
    desactivados = 0

    with transaction() as cur:
        if desactivar_faltantes:
            # Quien no viene en el archivo deja de participar; quien viene se reactiva
            cur.execute('UPDATE empleados SET activo = 0 WHERE activo = 1')
        cur.executemany(
            f'''INSERT INTO empleados (cue, nombre_completo, empresa, distrito, departamento, path_fotografia)
                VALUES (%s, %s, %s, %s, %s, %s) AS nuevo
                ON DUPLICATE KEY UPDATE
                    nombre_completo = nuevo.nombre_completo,
                    empresa = nuevo.empresa,
                    distrito = nuevo.distrito,
                    departamento = nuevo.departamento,
                    path_fotografia = nuevo.path_fotografia
                    {', activo = 1' if desactivar_faltantes else ''}''',
            [tuple(f[c] for c in CSV_COLUMNS) for f in filas],
        )
        if desactivar_faltantes:
            cur.execute('SELECT COUNT(*) AS n FROM empleados WHERE activo = 0')
            desactivados = cur.fetchone()['n']

    resultado = {
        'ok': True,
        'archivo': archivo.filename,
        'total': len(filas),
        'nuevos': nuevos,
        'actualizados': len(filas) - nuevos,
        'desactivados': desactivados,
    }
    registrar_bitacora('IMPORTAR_EMPLEADOS', resultado)
    session['resultado_importacion'] = resultado
    return redirect(url_for('admin.empleados'))
