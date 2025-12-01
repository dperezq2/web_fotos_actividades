FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    nginx \
    certbot \
    python3-certbot-nginx \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para cachear dependencias
COPY project/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY project/ /app/
COPY nginx.conf /etc/nginx/sites-available/default
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Crear directorios necesarios con permisos adecuados
RUN mkdir -p uploads static/img .flask_session /var/log/nginx /var/lib/nginx \
    && chmod -R 755 uploads static/img .flask_session

# Crear usuario no-root para mayor seguridad
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Dar permisos a nginx para los logs
RUN chown -R appuser:appuser /var/log/nginx /var/lib/nginx

USER appuser

# Variables de entorno
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Exponer puertos
EXPOSE 80 443 3000

# Script de inicio
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

CMD ["/app/start.sh"]