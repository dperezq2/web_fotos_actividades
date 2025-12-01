import pandas as pd
import random
from pathlib import Path
import csv
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SorteoManager:
    def __init__(self):
        self.df = None
        self.winners = []
        self.uploaded_file = None

    def _inspect_csv_file(self, file_path):
        """Lee las primeras líneas del CSV para detectar el formato y las columnas"""
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(2048)  # Leer solo los primeros bytes para inspección
            
        logger.info(f"Contenido inicial del CSV: {content[:500]}")
        return content

    def load_csv(self, file_path):
        """Carga y valida el archivo CSV con manejo ultra-robusto de formatos."""
        try:
            # Inspeccionar el contenido del archivo
            csv_preview = self._inspect_csv_file(file_path)
            logger.info(f"Inspeccionando archivo CSV: {file_path}")
            
            # FASE 1: Intentar diferentes métodos de lectura
            successful_read = False
            error_messages = []
            
            # Método 1: Pandas estándar
            try:
                self.df = pd.read_csv(file_path, encoding='utf-8')
                logger.info(f"Lectura exitosa con pandas estándar. Columnas: {self.df.columns.tolist()}")
                successful_read = True
            except Exception as e:
                error_messages.append(f"Método 1 (pandas estándar) falló: {str(e)}")
                logger.warning(f"Falló lectura con pandas estándar: {str(e)}")
                
                # Método 2: Pandas con parámetros específicos
                try:
                    self.df = pd.read_csv(file_path, encoding='utf-8', quotechar='"', 
                                        delimiter=',', escapechar='\\')
                    logger.info(f"Lectura exitosa con pandas específico. Columnas: {self.df.columns.tolist()}")
                    successful_read = True
                except Exception as e2:
                    error_messages.append(f"Método 2 (pandas específico) falló: {str(e2)}")
                    logger.warning(f"Falló lectura con pandas específico: {str(e2)}")
                    
                    # Método 3: CSV básico de Python
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                            csv_reader = csv.reader(f)
                            rows = list(csv_reader)
                            
                        if rows:
                            headers = [h.strip().strip('"').strip("'") for h in rows[0]]
                            data = []
                            for row in rows[1:]:
                                if row:  # Solo procesar filas no vacías
                                    # Asegurarse de que la fila tenga la longitud correcta
                                    while len(row) < len(headers):
                                        row.append('')
                                    if len(row) > len(headers):
                                        row = row[:len(headers)]
                                    data.append(row)
                            
                            self.df = pd.DataFrame(data, columns=headers)
                            logger.info(f"Lectura exitosa con csv básico. Columnas: {self.df.columns.tolist()}")
                            successful_read = True
                        else:
                            error_messages.append("El archivo CSV está vacío")
                    except Exception as e3:
                        error_messages.append(f"Método 3 (csv básico) falló: {str(e3)}")
                        logger.warning(f"Falló lectura con csv básico: {str(e3)}")
                        
                        # Método 4: Lectura manual línea por línea
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                                content = f.read()
                            
                            lines = content.split('\n')
                            if lines:
                                # Detectar separador (coma, punto y coma, tab)
                                separators = [',', ';', '\t']
                                separator = ','  # por defecto
                                for sep in separators:
                                    if sep in lines[0]:
                                        separator = sep
                                        break
                                
                                headers = [h.strip().strip('"').strip("'") for h in lines[0].split(separator)]
                                data = []
                                
                                for line in lines[1:]:
                                    if not line.strip():
                                        continue
                                    row = [cell.strip().strip('"').strip("'") for cell in line.split(separator)]
                                    while len(row) < len(headers):
                                        row.append('')
                                    if len(row) > len(headers):
                                        row = row[:len(headers)]
                                    data.append(row)
                                
                                self.df = pd.DataFrame(data, columns=headers)
                                logger.info(f"Lectura exitosa con método manual. Columnas: {self.df.columns.tolist()}")
                                successful_read = True
                            else:
                                error_messages.append("El archivo CSV está vacío")
                        except Exception as e4:
                            error_messages.append(f"Método 4 (manual) falló: {str(e4)}")
                            logger.error(f"Todos los métodos de lectura fallaron")
            
            if not successful_read:
                return False, f"No se pudo leer el archivo CSV. Errores: {'; '.join(error_messages)}"
            
            # FASE 2: Procesamiento de columnas
            # Normalizar nombres de columnas (quitar espacios, comillas, etc.)
            original_columns = self.df.columns.tolist()
            logger.info(f"Columnas originales: {original_columns}")
            
            # Limpiar nombres de columnas
            self.df.columns = [col.strip().strip('"').strip("'") for col in self.df.columns]
            logger.info(f"Columnas después de limpieza básica: {self.df.columns.tolist()}")
            
            # FASE 3: Mapeo inteligente de columnas
            required_cols = {'Empleado', 'CUE', 'PathFotografia'}
            available_cols = set(self.df.columns)
            
            # Diccionario para mapeo de variantes de nombres de columnas
            column_variants = {
                'Empleado': ['empleado', 'nombre', 'name', 'employee', 'nomempleado', 'nombre empleado', 'nombre_empleado'],
                'CUE': ['cue', 'codigo', 'code', 'id', 'num', 'numero', 'empleadoid', 'empleado_id', 'employee_id'],
                'PathFotografia': ['path', 'foto', 'photo', 'imagen', 'image', 'pathfoto', 'ruta', 'fotografía', 'fotografia']
            }
            
            # Mapeo de columnas
            column_mapping = {}
            for req_col in required_cols:
                if req_col not in available_cols:
                    # Buscar por variantes
                    for col in available_cols:
                        normalized_col = col.lower().replace(' ', '').replace('_', '')
                        # Buscar coincidencia exacta primero
                        if normalized_col == req_col.lower():
                            column_mapping[col] = req_col
                            break
                        # Luego buscar en variantes
                        if any(variant in normalized_col for variant in column_variants[req_col]):
                            column_mapping[col] = req_col
                            break
            
            # Mostrar mapeo encontrado
            if column_mapping:
                logger.info(f"Mapeo de columnas encontrado: {column_mapping}")
                self.df = self.df.rename(columns=column_mapping)
            
            # Verificar de nuevo después de renombrar
            missing_cols = required_cols - set(self.df.columns)
            if missing_cols:
                logger.error(f"Columnas faltantes después del mapeo: {missing_cols}")
                # Imprimimos todas las columnas disponibles para diagnóstico
                logger.info(f"Columnas disponibles: {self.df.columns.tolist()}")
                
                # Si solo faltan ciertas columnas, intentamos una asignación directa
                if len(self.df.columns) >= len(required_cols):
                    logger.info("Intentando asignación directa por posición")
                    # Intentar asignar por posición si hay suficientes columnas
                    new_columns = list(self.df.columns)
                    missing_list = list(missing_cols)
                    
                    # Usar las primeras columnas disponibles para las que faltan
                    for i, missing_col in enumerate(missing_list):
                        if i < len(new_columns):
                            # Reemplazar una columna existente con la que falta
                            old_col = new_columns[i]
                            column_mapping[old_col] = missing_col
                            
                    if column_mapping:
                        logger.info(f"Asignación directa: {column_mapping}")
                        self.df = self.df.rename(columns=column_mapping)
                        missing_cols = required_cols - set(self.df.columns)
            
            # Verificación final
            if missing_cols:
                # Mostrar muestra de datos para diagnóstico
                logger.error(f"No se pudieron encontrar las columnas requeridas: {missing_cols}")
                logger.info(f"Muestra del DataFrame:\n{self.df.head().to_string()}")
                return False, f"El archivo debe contener las columnas: {', '.join(required_cols)}. Columnas faltantes: {', '.join(missing_cols)}"
            
            # FASE 4: Limpieza de datos
            # Limpiar los datos en las columnas
            for col in self.df.columns:
                if self.df[col].dtype == object:  # Solo limpiar columnas de texto
                    self.df[col] = self.df[col].astype(str).apply(lambda x: x.strip().strip('"').strip("'"))
            
            # Manejar valores faltantes en PathFotografia
            self.df['PathFotografia'] = self.df['PathFotografia'].fillna('')
            self.df['PathFotografia'] = self.df['PathFotografia'].apply(
                lambda x: '' if x.lower() in ['nan', 'none', 'null', ''] else x
            )
            
            # Guardar el archivo para análisis si es necesario
            self.uploaded_file = file_path
            self.winners = []
            
            logger.info(f"Archivo procesado correctamente con {len(self.df)} empleados")
            return True, f"Archivo cargado correctamente. {len(self.df)} empleados encontrados."
        
        except Exception as e:
            logger.exception("Error no controlado al procesar el CSV")
            return False, f"Error al procesar el archivo: {str(e)}"

    def get_winners(self, num_winners):
        """Selecciona ganadores aleatorios excluyendo ganadores previos."""
        if self.df is None:
            return False, "No se ha cargado ningún archivo"
        
        try:
            # Filtrar ganadores previos por CUE
            previous_winner_cues = [w['CUE'] for w in self.winners] if self.winners else []
            available = self.df if not previous_winner_cues else self.df[~self.df['CUE'].isin(previous_winner_cues)]
            
            if len(available) < num_winners:
                return False, f"No hay suficientes empleados disponibles ({len(available)} restantes)"
            
            # Seleccionar ganadores aleatorios
            winners = available.sample(n=num_winners).to_dict('records')
            self.winners.extend(winners)
            return True, winners
        except Exception as e:
            logger.exception("Error al seleccionar ganadores")
            return False, f"Error al seleccionar ganadores: {str(e)}"

    def reset_sorteo(self):
        """Reinicia el sorteo manteniendo el archivo cargado."""
        self.winners = []
        return True, "Sorteo reiniciado. Todos los empleados están disponibles nuevamente."

    def has_file(self):
        """Verifica si hay un archivo cargado."""
        return self.df is not None and not self.df.empty

    def get_sample_data(self):
        """Devuelve una muestra del DataFrame para diagnóstico."""
        if self.df is None:
            return "No hay datos cargados"
        return self.df.head(5).to_string()