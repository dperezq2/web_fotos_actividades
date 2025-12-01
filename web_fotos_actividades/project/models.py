import sqlite3
from datetime import datetime
from pathlib import Path
import json
import logging

# Configurar logger para models
logger = logging.getLogger(__name__)

# Nombre de la base de datos
DB_NAME = 'sorteos_historico.db'

class Database:
    """Manejador de la base de datos de sorteos"""
    
    def __init__(self, db_path=DB_NAME):
        self.db_path = db_path
        logger.info(f"🔧 Inicializando base de datos: {db_path}")
        try:
            self.init_database()
            logger.info(f"✅ Base de datos inicializada correctamente")
        except Exception as e:
            logger.error(f"❌ Error al inicializar BD: {e}")
            raise
    
    def get_connection(self):
        """Obtiene una conexión a la base de datos"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Permite acceder a columnas por nombre
        return conn
    
    def init_database(self):
        """Inicializa la base de datos con las tablas necesarias"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Crear tabla de sorteos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sorteos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_archivo TEXT NOT NULL,
                fecha_sorteo TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_participantes INTEGER NOT NULL,
                num_ganadores INTEGER NOT NULL,
                descripcion TEXT
            )
        ''')
        
        # Crear tabla de ganadores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ganadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sorteo_id INTEGER NOT NULL,
                cue TEXT NOT NULL,
                nombre_empleado TEXT NOT NULL,
                numero_ganador INTEGER NOT NULL,
                path_fotografia TEXT,
                datos_adicionales TEXT,
                FOREIGN KEY (sorteo_id) REFERENCES sorteos(id) ON DELETE CASCADE
            )
        ''')
        
        # Crear índices para mejorar el rendimiento
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ganadores_sorteo 
            ON ganadores(sorteo_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_ganadores_cue 
            ON ganadores(cue)
        ''')
        
        conn.commit()
        conn.close()
    
    def guardar_sorteo(self, nombre_archivo, total_participantes, num_ganadores, descripcion=None):
        """
        Guarda un nuevo sorteo en la base de datos
        
        Returns:
            int: ID del sorteo creado
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO sorteos (nombre_archivo, total_participantes, num_ganadores, descripcion)
            VALUES (?, ?, ?, ?)
        ''', (nombre_archivo, total_participantes, num_ganadores, descripcion))
        
        sorteo_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return sorteo_id
    
    def guardar_ganadores(self, sorteo_id, ganadores):
        """
        Guarda los ganadores de un sorteo
        
        Args:
            sorteo_id (int): ID del sorteo
            ganadores (list): Lista de diccionarios con datos de ganadores
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        for idx, ganador in enumerate(ganadores, start=1):
            # Extraer campos principales
            cue = ganador.get('CUE', '')
            nombre = ganador.get('Empleado', 'Sin nombre')
            path_foto = ganador.get('PathFotografia', '')
            
            # Guardar datos adicionales como JSON
            datos_adicionales = {k: v for k, v in ganador.items() 
                               if k not in ['CUE', 'Empleado', 'PathFotografia']}
            datos_json = json.dumps(datos_adicionales)
            
            cursor.execute('''
                INSERT INTO ganadores 
                (sorteo_id, cue, nombre_empleado, numero_ganador, path_fotografia, datos_adicionales)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (sorteo_id, cue, nombre, idx, path_foto, datos_json))
        
        conn.commit()
        conn.close()
    
    def obtener_sorteos(self, limit=None):
        """
        Obtiene todos los sorteos registrados
        
        Args:
            limit (int): Número máximo de sorteos a retornar
        
        Returns:
            list: Lista de sorteos
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = 'SELECT * FROM sorteos ORDER BY fecha_sorteo DESC'
        if limit:
            query += f' LIMIT {limit}'
        
        cursor.execute(query)
        sorteos = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return sorteos
    
    def obtener_sorteo(self, sorteo_id):
        """Obtiene un sorteo específico por su ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM sorteos WHERE id = ?', (sorteo_id,))
        sorteo = cursor.fetchone()
        conn.close()
        
        return dict(sorteo) if sorteo else None
    
    def obtener_ganadores_sorteo(self, sorteo_id):
        """
        Obtiene todos los ganadores de un sorteo específico
        
        Returns:
            list: Lista de ganadores con sus datos
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM ganadores 
            WHERE sorteo_id = ? 
            ORDER BY numero_ganador
        ''', (sorteo_id,))
        
        ganadores = []
        for row in cursor.fetchall():
            ganador = dict(row)
            # Parsear datos adicionales
            if ganador['datos_adicionales']:
                ganador['datos_adicionales'] = json.loads(ganador['datos_adicionales'])
            ganadores.append(ganador)
        
        conn.close()
        return ganadores
    
    def verificar_ganador_previo(self, cue):
        """
        Verifica si un empleado (CUE) ya ha ganado en algún sorteo anterior
        
        Returns:
            list: Lista de sorteos donde ha ganado
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT s.*, g.numero_ganador, g.nombre_empleado
            FROM ganadores g
            JOIN sorteos s ON g.sorteo_id = s.id
            WHERE g.cue = ?
            ORDER BY s.fecha_sorteo DESC
        ''', (cue,))
        
        resultados = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return resultados
    
    def obtener_estadisticas(self):
        """
        Obtiene estadísticas generales de los sorteos
        
        Returns:
            dict: Estadísticas actualizadas en tiempo real
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Total de sorteos ACTIVOS (que aún existen)
        cursor.execute('SELECT COUNT(*) as total FROM sorteos')
        total_sorteos = cursor.fetchone()['total']
        
        # Total de ganadores ACTIVOS (solo de sorteos existentes)
        # Usamos INNER JOIN para contar solo ganadores de sorteos que no han sido eliminados
        cursor.execute('''
            SELECT COUNT(g.id) as total 
            FROM ganadores g
            INNER JOIN sorteos s ON g.sorteo_id = s.id
        ''')
        total_ganadores = cursor.fetchone()['total']
        
        # Último sorteo
        cursor.execute('SELECT * FROM sorteos ORDER BY fecha_sorteo DESC LIMIT 1')
        ultimo_sorteo = cursor.fetchone()
        
        conn.close()
        
        return {
            'total_sorteos': total_sorteos,
            'total_ganadores': total_ganadores,
            'ultimo_sorteo': dict(ultimo_sorteo) if ultimo_sorteo else None
        }
    
    def eliminar_sorteo(self, sorteo_id):
        """
        Elimina un sorteo y todos sus ganadores (CASCADE)
        
        Returns:
            bool: True si se eliminó correctamente
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM sorteos WHERE id = ?', (sorteo_id,))
        affected = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return affected > 0


# Función auxiliar para inicializar la base de datos al importar el módulo
def init_db():
    """Inicializa la base de datos si no existe"""
    db = Database()
    return db


# Crear instancia global
db = init_db()