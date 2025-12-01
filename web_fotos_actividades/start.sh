#!/bin/bash

# Crear directorios necesarios
mkdir -p uploads/{cena-gerentes,sesion-gerentes-rrhh,convivio,actividad-bananero}
mkdir -p static/img database logs .flask_session /var/www/certbot

# Configuración inicial de la aplicación
echo "🔧 Configurando aplicación de sorteos y fotos..."

# Iniciar la aplicación Flask en segundo plano
echo "🚀 Iniciando aplicación Flask..."
python app.py &

# Esperar a que Flask esté listo
echo "⏳ Esperando que Flask inicie..."
sleep 15

# Verificar que Flask esté corriendo
if curl -f http://localhost:3000/ > /dev/null 2>&1; then
    echo "✅ Flask está corriendo correctamente"
else
    echo "❌ Flask no está respondiendo, reintentando..."
    sleep 10
fi

# Configurar Nginx y SSL
echo "🌐 Configurando Nginx y SSL..."

# Verificar si ya existe el certificado
if [ ! -f "/etc/letsencrypt/live/actividades.paloblancofreshfoods.com.gt/fullchain.pem" ]; then
    echo "📄 Obteniendo certificado SSL por primera vez..."
    
    # Iniciar nginx temporalmente para el desafío
    nginx -g 'daemon off;' &
    NGINX_PID=$!
    
    sleep 5
    
    # Obtener certificado
    certbot --nginx \
        --non-interactive \
        --agree-tos \
        --email admin@paloblancofreshfoods.com.gt \
        --domains actividades.paloblancofreshfoods.com.gt \
        --redirect \
        --keep-until-expiring || echo "⚠️ No se pudo obtener certificado inicial. Verifica DNS."
    
    # Detener nginx temporal
    kill $NGINX_PID 2>/dev/null || true
    sleep 3
else
    echo "🔄 Renovando certificado SSL existente..."
    certbot renew --quiet
fi

# Iniciar Nginx en primer plano
echo "🎯 Iniciando Nginx en primer plano..."
exec nginx -g "daemon off;"