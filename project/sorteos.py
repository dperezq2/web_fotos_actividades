"""Sorteos sobre MySQL: creación con filtros, ruleta, ganadores, PDF y mural.

Regla principal: quien gana una vez ya no participa en ningún otro sorteo
(lo garantiza el índice único ganadores.empleado_id).
"""
import csv
import io
import os
import random
import time
from datetime import datetime

import pymysql
from flask import (Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, url_for)

from auth import superadmin_required
from db import execute, query, registrar_bitacora, transaction

sorteos_bp = Blueprint('sorteos', __name__)

FILTROS = ('empresa', 'distrito', 'departamento')
MAX_POR_TIRADA = 50
NOMBRES_ANIMACION = 80
POR_PAGINA = 50
# Si la ruleta se cierra a medio revelar, el mural muestra igual a los pendientes tras este tiempo
MINUTOS_REVELADO_AUTOMATICO = 10
REINTENTABLES = (1213, 1205)  # Deadlock y espera de bloqueo: MySQL pide reintentar
ESTADOS = {
    'BORRADOR': ('Sin iniciar', 'tag--muted'),
    'EN_CURSO': ('En curso', ''),
    'FINALIZADO': ('Finalizado', 'tag--dark'),
}
MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre')

_random = random.SystemRandom()


@sorteos_bp.app_template_filter('fecha')
def formato_fecha(valor, con_hora=True):
    if not valor:
        return ''
    texto = f'{valor.day} de {MESES[valor.month - 1]} de {valor.year}'
    return f"{texto}, {valor.strftime('%H:%M')}" if con_hora else texto


@sorteos_bp.app_context_processor
def inyectar_estados():
    return {'ESTADOS_SORTEO': ESTADOS}


def _where(seleccion):
    """WHERE para los valores elegidos ({'empresa': [...], ...}). Los campos salen de FILTROS (seguros)."""
    condiciones, params = [], []
    for campo, valores in seleccion.items():
        if valores:
            condiciones.append(f"{campo} IN ({', '.join(['%s'] * len(valores))})")
            params += valores
    return (' AND '.join(condiciones) or '1 = 1'), params


def resolver_filtros(fuente):
    """Filtros en cascada: empresa -> distrito -> departamento.

    Las opciones de cada grupo dependen de lo elegido en los anteriores, y lo elegido
    que ya no existe (p. ej. un distrito sin empleados en la empresa marcada) se descarta.
    Devuelve (opciones, seleccion, total de participantes).
    """
    opciones, seleccion = {}, {}
    for campo in FILTROS:
        where, params = _where(seleccion)
        opciones[campo] = query(
            f'''SELECT {campo} AS valor, COUNT(*) AS n FROM v_empleados_elegibles
                WHERE {campo} IS NOT NULL AND {campo} <> '' AND {where}
                GROUP BY {campo} ORDER BY {campo}''', params)
        disponibles = {o['valor'] for o in opciones[campo]}
        seleccion[campo] = [v for v in fuente.getlist(campo) if v in disponibles]

    where, params = _where(seleccion)
    total = query(f'SELECT COUNT(*) AS n FROM v_empleados_elegibles WHERE {where}', params, one=True)['n']
    return opciones, seleccion, total


def _obtener_sorteo(sorteo_id):
    sorteo = query(
        '''SELECT s.*, u.nombre AS creado_por_nombre
           FROM sorteos s LEFT JOIN usuarios u ON u.id = s.creado_por
           WHERE s.id = %s''', (sorteo_id,), one=True)
    if not sorteo:
        abort(404)
    return sorteo


POOL_SQL = '''
    FROM sorteo_participantes sp
    JOIN empleados e ON e.id = sp.empleado_id
    LEFT JOIN ganadores g ON g.empleado_id = e.id
    WHERE sp.sorteo_id = %s AND e.activo = 1 AND g.id IS NULL
'''


def _restantes(sorteo_id, cur=None):
    sql = 'SELECT COUNT(*) AS n ' + POOL_SQL
    if cur:
        cur.execute(sql, (sorteo_id,))
        return cur.fetchone()['n']
    return query(sql, (sorteo_id,), one=True)['n']


def _ganadores_de(sorteo_id):
    return query(
        '''SELECT g.id, g.posicion, g.cue, g.nombre_empleado AS nombre, g.fecha,
                  e.empresa, e.distrito, e.departamento
           FROM ganadores g JOIN empleados e ON e.id = g.empleado_id
           WHERE g.sorteo_id = %s ORDER BY g.posicion''', (sorteo_id,))


# ==================== Inicio ====================

@sorteos_bp.route('/')
def inicio():
    resumen = query(
        '''SELECT (SELECT COUNT(*) FROM v_empleados_elegibles) AS elegibles,
                  (SELECT COUNT(*) FROM ganadores) AS ganadores,
                  (SELECT COUNT(*) FROM sorteos) AS sorteos,
                  (SELECT COUNT(*) FROM empleados) AS empleados''', one=True)
    sorteos = query(
        '''SELECT s.*, COUNT(g.id) AS num_ganadores
           FROM sorteos s LEFT JOIN ganadores g ON g.sorteo_id = s.id
           GROUP BY s.id ORDER BY s.created_at DESC''')
    return render_template('sorteos/inicio.html', resumen=resumen, sorteos=sorteos)


# ==================== Nuevo sorteo ====================

@sorteos_bp.route('/sorteos/opciones')
def opciones_filtros():
    opciones, seleccion, total = resolver_filtros(request.args)
    return jsonify({'opciones': opciones, 'seleccion': seleccion, 'total': total})


@sorteos_bp.route('/sorteos/nuevo', methods=['GET', 'POST'])
def nuevo():
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip() or None
        if not nombre or len(nombre) > 120:
            flash('Escribe un nombre para el sorteo (máximo 120 caracteres)', 'error')
        else:
            _, seleccion, _ = resolver_filtros(request.form)
            where, params = _where(seleccion)
            with transaction() as cur:
                cur.execute('INSERT INTO sorteos (nombre, descripcion, creado_por) VALUES (%s, %s, %s)',
                            (nombre, descripcion[:255] if descripcion else None, g.user['id']))
                sorteo_id = cur.lastrowid
                cur.execute(
                    f'''INSERT INTO sorteo_participantes (sorteo_id, empleado_id)
                        SELECT %s, id FROM v_empleados_elegibles WHERE {where}''',
                    [sorteo_id] + params)
                total = cur.rowcount
                if total == 0:
                    raise _SinParticipantes()
                cur.execute('UPDATE sorteos SET total_participantes = %s WHERE id = %s', (total, sorteo_id))
            filtros = {c: v for c, v in seleccion.items() if v}
            registrar_bitacora('CREAR_SORTEO', {'sorteo_id': sorteo_id, 'nombre': nombre,
                                                'participantes': total, 'filtros': filtros})
            return redirect(url_for('sorteos.ruleta', sorteo_id=sorteo_id))

    opciones, seleccion, total = resolver_filtros(request.form)
    return render_template('sorteos/nuevo.html', opciones=opciones, seleccion=seleccion, total=total,
                           form=request.form)


class _SinParticipantes(Exception):
    pass


@sorteos_bp.errorhandler(_SinParticipantes)
def sin_participantes(error):
    flash('Ningún empleado cumple con los filtros elegidos (o todos ya ganaron)', 'error')
    return redirect(url_for('sorteos.nuevo'))


# ==================== Ruleta ====================

@sorteos_bp.route('/sorteos/<int:sorteo_id>')
def ruleta(sorteo_id):
    sorteo = _obtener_sorteo(sorteo_id)
    return render_template('sorteos/ruleta.html', sorteo=sorteo, ganadores=_ganadores_de(sorteo_id),
                           restantes=_restantes(sorteo_id), max_por_tirada=MAX_POR_TIRADA)


class _TiradaRechazada(Exception):
    def __init__(self, mensaje, status):
        super().__init__(mensaje)
        self.mensaje, self.status = mensaje, status


def _ejecutar_tirada(sorteo_id, cantidad):
    """Elige y guarda los ganadores en una sola transacción. Devuelve (ganadores, pool)."""
    with transaction() as cur:
        # Bloquea el sorteo: dos personas no pueden sortear el mismo a la vez
        cur.execute('SELECT id, estado FROM sorteos WHERE id = %s FOR UPDATE', (sorteo_id,))
        sorteo = cur.fetchone()
        if not sorteo:
            raise _TiradaRechazada('Sorteo no encontrado', 404)
        if sorteo['estado'] == 'FINALIZADO':
            raise _TiradaRechazada('Este sorteo ya fue finalizado', 409)

        cur.execute('SELECT e.id, e.cue, e.nombre_completo, e.empresa, e.distrito, e.departamento '
                    + POOL_SQL, (sorteo_id,))
        pool = cur.fetchall()
        if len(pool) < cantidad:
            raise _TiradaRechazada(f'Solo quedan {len(pool)} participantes disponibles', 409)

        elegidos = _random.sample(pool, cantidad)
        cur.execute('SELECT COALESCE(MAX(posicion), 0) AS ultima FROM ganadores WHERE sorteo_id = %s',
                    (sorteo_id,))
        posicion = cur.fetchone()['ultima']

        ganadores = []
        for empleado in elegidos:
            posicion += 1
            cur.execute(
                '''INSERT INTO ganadores (sorteo_id, empleado_id, cue, nombre_empleado, posicion, realizado_por)
                   VALUES (%s, %s, %s, %s, %s, %s)''',
                (sorteo_id, empleado['id'], empleado['cue'], empleado['nombre_completo'], posicion,
                 g.user['id']))
            ganadores.append({
                'id': cur.lastrowid, 'posicion': posicion, 'cue': empleado['cue'],
                'nombre': empleado['nombre_completo'], 'empresa': empleado['empresa'],
                'distrito': empleado['distrito'], 'departamento': empleado['departamento'],
            })
        cur.execute("UPDATE sorteos SET estado = 'EN_CURSO' WHERE id = %s AND estado = 'BORRADOR'",
                    (sorteo_id,))
    return ganadores, pool


@sorteos_bp.route('/sorteos/<int:sorteo_id>/sortear', methods=['POST'])
def sortear(sorteo_id):
    datos = request.get_json(silent=True) or request.form
    try:
        cantidad = int(datos.get('cantidad', 1))
    except (TypeError, ValueError):
        cantidad = 0
    if not 1 <= cantidad <= MAX_POR_TIRADA:
        return jsonify({'ok': False, 'mensaje': f'La cantidad debe estar entre 1 y {MAX_POR_TIRADA}'}), 400

    for intento in range(5):
        if intento:
            time.sleep(_random.uniform(0.05, 0.25) * intento)  # Evita volver a chocar al mismo ritmo
        try:
            ganadores, pool = _ejecutar_tirada(sorteo_id, cantidad)
            break
        except _TiradaRechazada as rechazo:
            return jsonify({'ok': False, 'mensaje': rechazo.mensaje}), rechazo.status
        except pymysql.err.IntegrityError:
            # Otro sorteo eligió a la misma persona en el mismo instante: se vuelve a sortear
            continue
        except pymysql.err.OperationalError as error:
            if error.args[0] in REINTENTABLES:
                continue
            raise
    else:
        return jsonify({'ok': False, 'mensaje': 'Hay otro sorteo en curso al mismo tiempo. Intenta de nuevo.'}), 409

    registrar_bitacora('EJECUTAR_SORTEO', {'sorteo_id': sorteo_id,
                                           'ganadores': [w['cue'] for w in ganadores]})

    # Nombres para la animación (no influyen en el resultado, que ya está decidido)
    elegidos = {w['cue'] for w in ganadores}
    restantes = [p['nombre_completo'] for p in pool if p['cue'] not in elegidos]
    nombres = _random.sample(restantes, min(len(restantes), NOMBRES_ANIMACION)) + [w['nombre'] for w in ganadores]
    return jsonify({'ok': True, 'ganadores': ganadores, 'restantes': len(pool) - cantidad, 'nombres': nombres})


@sorteos_bp.route('/sorteos/<int:sorteo_id>/revelar', methods=['POST'])
def revelar(sorteo_id):
    """La ruleta avisa qué ganadores ya mostró, para que el mural los vaya agregando uno a uno."""
    datos = request.get_json(silent=True) or {}
    ids = [i for i in datos.get('ids', []) if isinstance(i, int)][:MAX_POR_TIRADA]
    if ids:
        execute(
            f'''UPDATE ganadores SET revelado_at = NOW()
                WHERE sorteo_id = %s AND revelado_at IS NULL AND id IN ({', '.join(['%s'] * len(ids))})''',
            [sorteo_id] + ids)
    return jsonify({'ok': True})


@sorteos_bp.route('/sorteos/<int:sorteo_id>/finalizar', methods=['POST'])
def finalizar(sorteo_id):
    sorteo = _obtener_sorteo(sorteo_id)
    execute("UPDATE sorteos SET estado = 'FINALIZADO', finalizado_at = NOW() WHERE id = %s", (sorteo_id,))
    registrar_bitacora('FINALIZAR_SORTEO', {'sorteo_id': sorteo_id})
    flash(f"Sorteo «{sorteo['nombre']}» finalizado", 'success')
    return redirect(url_for('sorteos.ruleta', sorteo_id=sorteo_id))


@sorteos_bp.route('/sorteos/<int:sorteo_id>/reabrir', methods=['POST'])
@superadmin_required
def reabrir(sorteo_id):
    _obtener_sorteo(sorteo_id)
    execute("UPDATE sorteos SET estado = 'EN_CURSO', finalizado_at = NULL WHERE id = %s", (sorteo_id,))
    registrar_bitacora('REABRIR_SORTEO', {'sorteo_id': sorteo_id})
    flash('Sorteo reabierto', 'success')
    return redirect(url_for('sorteos.ruleta', sorteo_id=sorteo_id))


@sorteos_bp.route('/sorteos/<int:sorteo_id>/eliminar', methods=['POST'])
@superadmin_required
def eliminar(sorteo_id):
    sorteo = _obtener_sorteo(sorteo_id)
    execute('DELETE FROM sorteos WHERE id = %s', (sorteo_id,))
    registrar_bitacora('ELIMINAR_SORTEO', {'sorteo_id': sorteo_id, 'nombre': sorteo['nombre']})
    flash(f"Sorteo «{sorteo['nombre']}» eliminado. Sus ganadores vuelven a participar.", 'success')
    return redirect(url_for('sorteos.inicio'))


@sorteos_bp.route('/sorteos/<int:sorteo_id>/ganadores/<int:ganador_id>/quitar', methods=['POST'])
@superadmin_required
def quitar_ganador(sorteo_id, ganador_id):
    ganador = query('SELECT id, cue, nombre_empleado FROM ganadores WHERE id = %s AND sorteo_id = %s',
                    (ganador_id, sorteo_id), one=True)
    if ganador:
        execute('DELETE FROM ganadores WHERE id = %s', (ganador_id,))
        registrar_bitacora('QUITAR_GANADOR', {'sorteo_id': sorteo_id, 'cue': ganador['cue']})
        flash(f"{ganador['nombre_empleado']} ya no es ganador y vuelve a participar", 'success')
    return redirect(url_for('sorteos.ruleta', sorteo_id=sorteo_id))


# ==================== PDF ====================

@sorteos_bp.route('/sorteos/<int:sorteo_id>/pdf')
def pdf(sorteo_id):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    sorteo = _obtener_sorteo(sorteo_id)
    ganadores = _ganadores_de(sorteo_id)
    verde = colors.HexColor('#1f5f02')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title=sorteo['nombre'],
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    titulo = ParagraphStyle('titulo', fontName='Helvetica-Bold', fontSize=17, leading=21, textColor=verde)
    texto = ParagraphStyle('texto', fontName='Helvetica', fontSize=10, leading=14, textColor=colors.HexColor('#444444'))
    celda = ParagraphStyle('celda', fontName='Helvetica', fontSize=10, leading=12)

    logo = Image(str(_ruta_static('img/logo_PB.jpg')), width=1.8 * cm, height=1.8 * cm)
    encabezado = Table([[logo, [Paragraph(sorteo['nombre'], titulo),
                                Paragraph(f"Realizado el {formato_fecha(sorteo['created_at'])}", texto)]]],
                       colWidths=[2.3 * cm, None])
    encabezado.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))

    elementos = [encabezado, Spacer(1, 8)]
    if sorteo['descripcion']:
        elementos.append(Paragraph(sorteo['descripcion'], texto))
    elementos += [
        Paragraph(f"Participantes: <b>{sorteo['total_participantes']}</b> · Ganadores: <b>{len(ganadores)}</b>", texto),
        Spacer(1, 14),
    ]

    filas = [['#', 'CUE', 'Empleado', 'Empresa', 'Distrito']]
    for w in ganadores:
        filas.append([w['posicion'], w['cue'], Paragraph(w['nombre'], celda),
                      Paragraph(w['empresa'] or '—', celda), Paragraph(w['distrito'] or '—', celda)])
    tabla = Table(filas, colWidths=[1.1 * cm, 1.8 * cm, None, 3.4 * cm, 3 * cm], repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), verde),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#eef6e8')]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor('#cfdcc6')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elementos.append(tabla if ganadores else Paragraph('Este sorteo aún no tiene ganadores.', texto))

    doc.build(elementos)
    buffer.seek(0)
    nombre_archivo = f'sorteo_{sorteo_id}.pdf'
    return Response(buffer.getvalue(), mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename={nombre_archivo}'})


def _ruta_static(relativa):
    return os.path.join(current_app.static_folder, relativa)


# ==================== Ganadores ====================

def _consulta_ganadores(args):
    q = args.get('q', '').strip()
    sorteo_id = args.get('sorteo', type=int)
    condiciones, params = [], []
    if q:
        condiciones.append('(g.cue LIKE %s OR g.nombre_empleado LIKE %s)')
        params += [f'%{q}%', f'%{q}%']
    if sorteo_id:
        condiciones.append('g.sorteo_id = %s')
        params.append(sorteo_id)
    where = ('WHERE ' + ' AND '.join(condiciones)) if condiciones else ''
    base = f'''FROM ganadores g
               JOIN sorteos s ON s.id = g.sorteo_id
               JOIN empleados e ON e.id = g.empleado_id
               LEFT JOIN usuarios u ON u.id = g.realizado_por
               {where}'''
    columnas = '''g.id, g.posicion, g.cue, g.nombre_empleado AS nombre, g.fecha, g.sorteo_id,
                  s.nombre AS sorteo, e.empresa, e.distrito, e.departamento, u.nombre AS realizado_por'''
    return base, columnas, params, q, sorteo_id


@sorteos_bp.route('/ganadores')
def ganadores():
    base, columnas, params, q, sorteo_id = _consulta_ganadores(request.args)
    pagina = max(request.args.get('pagina', 1, type=int), 1)
    total = query(f'SELECT COUNT(*) AS n {base}', params, one=True)['n']
    lista = query(f'SELECT {columnas} {base} ORDER BY g.fecha DESC, g.posicion DESC LIMIT %s OFFSET %s',
                  params + [POR_PAGINA, (pagina - 1) * POR_PAGINA])
    sorteos = query('SELECT id, nombre FROM sorteos ORDER BY created_at DESC')
    return render_template('sorteos/ganadores.html', ganadores=lista, sorteos=sorteos, q=q,
                           sorteo_id=sorteo_id, total=total, pagina=pagina,
                           total_paginas=max((total + POR_PAGINA - 1) // POR_PAGINA, 1))


@sorteos_bp.route('/ganadores.csv')
def ganadores_csv():
    base, columnas, params, _, _ = _consulta_ganadores(request.args)
    lista = query(f'SELECT {columnas} {base} ORDER BY g.sorteo_id, g.posicion', params)
    salida = io.StringIO()
    writer = csv.writer(salida)
    writer.writerow(['sorteo', 'posicion', 'cue', 'nombre', 'empresa', 'distrito', 'departamento', 'fecha'])
    for w in lista:
        writer.writerow([w['sorteo'], w['posicion'], w['cue'], w['nombre'], w['empresa'] or '',
                         w['distrito'] or '', w['departamento'] or '', w['fecha'].strftime('%Y-%m-%d %H:%M')])
    return Response('﻿' + salida.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f"attachment; filename=ganadores_{datetime.now():%Y%m%d}.csv"})


# ==================== Mural (para proyectar) ====================

@sorteos_bp.route('/mural')
def mural():
    sorteo_id = request.args.get('sorteo', type=int)
    sorteo = _obtener_sorteo(sorteo_id) if sorteo_id else None
    return render_template('sorteos/mural.html', sorteo=sorteo)


@sorteos_bp.route('/api/ganadores')
def api_ganadores():
    """Ganadores ya revelados en la ruleta, en el orden en que aparecieron."""
    sorteo_id = request.args.get('sorteo', type=int)
    condiciones = ['(g.revelado_at IS NOT NULL OR g.fecha < NOW() - INTERVAL %s MINUTE)']
    params = [MINUTOS_REVELADO_AUTOMATICO]
    if sorteo_id:
        condiciones.append('g.sorteo_id = %s')
        params.append(sorteo_id)
    lista = query(
        f'''SELECT g.id, g.nombre_empleado AS nombre, g.posicion, s.nombre AS sorteo
            FROM ganadores g JOIN sorteos s ON s.id = g.sorteo_id
            WHERE {' AND '.join(condiciones)}
            ORDER BY COALESCE(g.revelado_at, g.fecha), g.sorteo_id, g.posicion''', params)
    response = jsonify({'ganadores': lista, 'total': len(lista)})
    response.headers['Cache-Control'] = 'no-store'
    return response
