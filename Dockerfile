FROM python:3.12-slim

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

# Nginx necesita root para los puertos 80/443 y certbot para /etc/letsencrypt;
# los procesos de trabajo de nginx bajan de privilegios por sí solos.

# Variables de entorno
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Exponer puertos
EXPOSE 80 443 3000

# Script de inicio
COPY --chmod=755 start.sh /app/start.sh

CMD ["/app/start.sh"]
