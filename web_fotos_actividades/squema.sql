-- ============================================
-- Base de Datos: sorteos_historico.db
-- Sistema de Gestión de Sorteos Palo Blanco
-- ============================================

-- Eliminar tablas si existen (solo para reiniciar)
-- DROP TABLE IF EXISTS ganadores;
-- DROP TABLE IF EXISTS sorteos;

-- ============================================
-- Tabla: sorteos
-- Almacena información de cada sorteo realizado
-- ============================================
CREATE TABLE IF NOT EXISTS sorteos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_archivo TEXT NOT NULL,              -- Nombre del CSV original
    fecha_sorteo TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Fecha y hora del sorteo
    total_participantes INTEGER NOT NULL,      -- Total de empleados en el CSV
    num_ganadores INTEGER NOT NULL,            -- Cantidad de ganadores seleccionados
    descripcion TEXT                           -- Descripción opcional del sorteo
);

-- ============================================
-- Tabla: ganadores
-- Almacena los ganadores de cada sorteo
-- ============================================
CREATE TABLE IF NOT EXISTS ganadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sorteo_id INTEGER NOT NULL,                -- ID del sorteo (FK)
    cue TEXT NOT NULL,                         -- Código Único de Empleado
    nombre_empleado TEXT NOT NULL,             -- Nombre completo del empleado
    numero_ganador INTEGER NOT NULL,           -- Posición del ganador (1, 2, 3...)
    path_fotografia TEXT,                      -- Ruta de la fotografía
    datos_adicionales TEXT,                    -- JSON con datos extra del CSV
    
    -- Clave foránea con eliminación en cascada
    FOREIGN KEY (sorteo_id) REFERENCES sorteos(id) ON DELETE CASCADE
);

-- ============================================
-- Índices para optimizar consultas
-- ============================================

-- Índice para búsquedas por sorteo
CREATE INDEX IF NOT EXISTS idx_ganadores_sorteo 
ON ganadores(sorteo_id);

-- Índice para búsquedas por CUE
CREATE INDEX IF NOT EXISTS idx_ganadores_cue 
ON ganadores(cue);

-- Índice para ordenar sorteos por fecha
CREATE INDEX IF NOT EXISTS idx_sorteos_fecha 
ON sorteos(fecha_sorteo DESC);

-- ============================================
-- Comentarios sobre la estructura
-- ============================================

/*
TABLA sorteos:
- id: Identificador único autoincremental
- nombre_archivo: Ej. "empleados_diciembre_2024.csv"
- fecha_sorteo: Se registra automáticamente al crear el sorteo
- total_participantes: Número de filas del CSV
- num_ganadores: Cuántos ganadores se seleccionaron
- descripcion: Opcional, ej. "Sorteo Navideño 2024"

TABLA ganadores:
- id: Identificador único autoincremental
- sorteo_id: Relaciona al ganador con su sorteo
- cue: Código del empleado (debe coincidir con el CSV)
- nombre_empleado: Nombre del ganador
- numero_ganador: 1 = primer lugar, 2 = segundo, etc.
- path_fotografia: Ruta de la foto del empleado
- datos_adicionales: JSON con otros campos del CSV (departamento, puesto, etc.)

RELACIÓN:
Un sorteo puede tener muchos ganadores (1:N)
Si se elimina un sorteo, se eliminan sus ganadores (CASCADE)
*/

-- ============================================
-- Consultas útiles de ejemplo
-- ============================================

-- Ver todos los sorteos
-- SELECT * FROM sorteos ORDER BY fecha_sorteo DESC;

-- Ver ganadores de un sorteo específico
-- SELECT * FROM ganadores WHERE sorteo_id = 1 ORDER BY numero_ganador;

-- Ver todos los sorteos donde ganó un empleado
-- SELECT s.*, g.numero_ganador 
-- FROM ganadores g 
-- JOIN sorteos s ON g.sorteo_id = s.id 
-- WHERE g.cue = '12345';

-- Estadísticas generales
-- SELECT COUNT(*) as total_sorteos FROM sorteos;
-- SELECT COUNT(*) as total_ganadores FROM ganadores;

-- Último sorteo realizado
-- SELECT * FROM sorteos ORDER BY fecha_sorteo DESC LIMIT 1;