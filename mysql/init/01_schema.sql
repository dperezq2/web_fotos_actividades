-- ============================================================
-- Sistema de Sorteos Palo Blanco - Esquema MySQL 8
-- Se ejecuta automáticamente solo la primera vez que se crea el
-- volumen de MySQL (docker-entrypoint-initdb.d).
-- ============================================================

SET NAMES utf8mb4;

-- ------------------------------------------------------------
-- usuarios: acceso al módulo de sorteos (login con CUE)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    cue             VARCHAR(10)  NOT NULL,                 -- Usuario de login
    nombre          VARCHAR(150) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,                 -- Nunca la contraseña en texto plano
    rol             ENUM('SUPERADMIN', 'USUARIO') NOT NULL DEFAULT 'USUARIO',
    activo          TINYINT(1)   NOT NULL DEFAULT 1,        -- Quitar acceso sin borrar
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_usuarios_cue (cue)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------
-- empleados: personal que puede participar (se carga por CSV)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS empleados (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    cue             VARCHAR(10)  NOT NULL,                 -- Texto: conserva ceros a la izquierda
    nombre_completo VARCHAR(150) NOT NULL,
    empresa         VARCHAR(60)  NULL,
    distrito        VARCHAR(60)  NULL,
    departamento    VARCHAR(80)  NULL,
    path_fotografia VARCHAR(255) NULL,
    activo          TINYINT(1)   NOT NULL DEFAULT 1,        -- 0 = no participa en sorteos
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_empleados_cue (cue),
    KEY idx_empleados_filtros (empresa, distrito, departamento)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------
-- sorteos: cada evento de sorteo
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sorteos (
    id                  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    nombre              VARCHAR(120) NOT NULL,             -- Ej. "Convivio 2025 - Distrito 1"
    descripcion         VARCHAR(255) NULL,
    estado              ENUM('BORRADOR', 'EN_CURSO', 'FINALIZADO') NOT NULL DEFAULT 'BORRADOR',
    total_participantes INT UNSIGNED NOT NULL DEFAULT 0,
    creado_por          INT UNSIGNED NULL,
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finalizado_at       DATETIME     NULL,
    PRIMARY KEY (id),
    KEY idx_sorteos_fecha (created_at),
    CONSTRAINT fk_sorteos_usuario FOREIGN KEY (creado_por)
        REFERENCES usuarios (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------
-- sorteo_participantes: quién entra en cada sorteo (reemplaza al CSV)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sorteo_participantes (
    sorteo_id       INT UNSIGNED NOT NULL,
    empleado_id     INT UNSIGNED NOT NULL,
    PRIMARY KEY (sorteo_id, empleado_id),
    KEY idx_participantes_empleado (empleado_id),
    CONSTRAINT fk_participantes_sorteo FOREIGN KEY (sorteo_id)
        REFERENCES sorteos (id) ON DELETE CASCADE,
    CONSTRAINT fk_participantes_empleado FOREIGN KEY (empleado_id)
        REFERENCES empleados (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------
-- ganadores
-- uq_ganadores_empleado garantiza que una persona gane una sola vez
-- en todos los sorteos. Si se elimina un sorteo, sus ganadores se
-- eliminan (CASCADE) y esas personas vuelven a poder participar.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ganadores (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    sorteo_id       INT UNSIGNED NOT NULL,
    empleado_id     INT UNSIGNED NOT NULL,
    cue             VARCHAR(10)  NOT NULL,                 -- Copia para historial y PDF
    nombre_empleado VARCHAR(150) NOT NULL,
    posicion        INT UNSIGNED NOT NULL,                 -- 1, 2, 3...
    realizado_por   INT UNSIGNED NULL,                     -- Usuario que ejecutó la ruleta
    fecha           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revelado_at     DATETIME     NULL,                     -- Cuándo apareció en la ruleta (mural)
    PRIMARY KEY (id),
    UNIQUE KEY uq_ganadores_empleado (empleado_id),
    UNIQUE KEY uq_ganadores_posicion (sorteo_id, posicion),
    KEY idx_ganadores_fecha (fecha),
    CONSTRAINT fk_ganadores_sorteo FOREIGN KEY (sorteo_id)
        REFERENCES sorteos (id) ON DELETE CASCADE,
    CONSTRAINT fk_ganadores_empleado FOREIGN KEY (empleado_id)
        REFERENCES empleados (id) ON DELETE RESTRICT,
    CONSTRAINT fk_ganadores_usuario FOREIGN KEY (realizado_por)
        REFERENCES usuarios (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------
-- bitacora: quién hizo qué (login, crear usuario, ejecutar sorteo...)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bitacora (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    usuario_id      INT UNSIGNED NULL,
    accion          VARCHAR(50)  NOT NULL,                 -- LOGIN, LOGIN_FALLIDO, EJECUTAR_SORTEO...
    detalle         JSON         NULL,
    ip              VARCHAR(45)  NULL,
    fecha           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_bitacora_fecha (fecha),
    KEY idx_bitacora_usuario (usuario_id),
    CONSTRAINT fk_bitacora_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------
-- Vista: empleados que todavía pueden participar
-- (activos y que nunca han ganado)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW v_empleados_elegibles AS
SELECT e.*
FROM empleados e
LEFT JOIN ganadores g ON g.empleado_id = e.id
WHERE e.activo = 1
  AND g.id IS NULL;
