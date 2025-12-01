#!/bin/bash

# Crear directorios necesarios
mkdir -p uploads/{cena-gerentes,sesion-gerentes-rrhh,convivio,actividad-bananero}
mkdir -p static/img database logs .flask_session /var/www/certbot

echo "🔧 Configurando aplicación de sorteos y fotos..."

# Iniciar Gunicorn en lugar del servidor interno de Flask
echo "🚀 Iniciando Gunicorn..."
gunicorn -b 0.0.0.0:3000 --workers 3 --timeout 180 app:app &
# ^^^ ESTO REEMPLAZA A 'python app.py &' COMPLETAMENTE

echo "⏳ Esperando que Gunicorn inicie..."
sleep 10

if curl -f http://localhost:3000/ > /dev/null 2>&1; then
    echo "✅ Gunicorn corriendo correctamente"
else
    echo "❌ Gunicorn no está respondiendo, reintentando..."
    sleep 10
fi

echo "🌐 Configurando Nginx y SSL..."

if [ ! -f "/etc/letsencrypt/live/actividades.paloblancofreshfoods.com.gt/fullchain.pem" ]; then
    echo "📄 Obteniendo certificado SSL por primera vez..."
    nginx -g 'daemon off;' &
    NGINX_PID=$!
    sleep 5

    certbot --nginx \
        --non-interactive \
        --agree-tos \
        --email admin@paloblancofreshfoods.com.gt \
        --domains actividades.paloblancofreshfoods.com.gt \
        --redirect \
        --keep-until-expiring || echo "⚠️ No se pudo obtener certificado inicial. Verifica DNS."

    kill $NGINX_PID 2>/dev/null || true
    sleep 3
else
    echo "🔄 Renovando certificados..."
    certbot renew --quiet
fi

echo "🎯 Iniciando Nginx en primer plano..."
exec nginx -g "daemon off;"
