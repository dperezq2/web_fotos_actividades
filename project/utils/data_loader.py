import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor

# Función para validar el URL de la foto (solo cuando sea necesario)
def validate_photo_path(url):
    try:
        response = requests.head(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

def load_participants(filepath):
    try:
        # Cargar el archivo CSV
        df = pd.read_csv(filepath)
        
        # Verificar que las columnas necesarias existan
        required_columns = ['Empleado', 'CUE', 'PathFotografia']
        for col in required_columns:
            if col not in df.columns:
                raise ValueError(f"Columna {col} no encontrada")
        
        # Agregar columna Excluido si no existe
        if 'Excluido' not in df.columns:
            df['Excluido'] = False
        
        # Filtrar los participantes no excluidos
        valid_participants = df[df['Excluido'] == False]
        
        # Crear la lista de participantes sin la validación de las fotos
        participants = []
        for _, row in valid_participants.iterrows():
            participant = {
                'Empleado': row['Empleado'],
                'CUE': row['CUE'],  # Agregar el CUE del participante
                'PathFotografia': row['PathFotografia']
            }
            participants.append(participant)
        
        if not participants:
            print("No se encontraron participantes válidos.")
        
        return participants
    
    except Exception as e:
        print(f"Error de carga: {e}")
        return []

# Función para validar la foto del ganador
def validate_winner_photo(winner_photo_url):
    # Validar la foto del ganador solo
    return validate_photo_path(winner_photo_url)

# Función para actualizar el archivo CSV y marcar un ganador como excluido
def update_participants_with_winner(filepath, winner_cue):
    try:
        # Leer el archivo CSV
        df = pd.read_csv(filepath)
        
        # Marcar al ganador como excluido
        df.loc[df['CUE'] == winner_cue, 'Excluido'] = True
        
        # Guardar el archivo actualizado
        df.to_csv(filepath, index=False)
        
    except Exception as e:
        print(f"Error al actualizar el archivo: {e}")
