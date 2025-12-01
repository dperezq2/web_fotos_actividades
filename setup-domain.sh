#!/bin/bash

DOMAIN="actividades.paloblancofreshfoods.com.gt"
EMAIL="admin@paloblancofreshfoods.com.gt"

echo "🔧 Configurando dominio: $DOMAIN"

# Verificar que estamos en el directorio correcto
if [ ! -d "project" ]; then
    echo "❌ Error: Debes ejecutar este script desde la raíz del proyecto"
    echo "   Estructura esperada:"
    echo "   web_fotos_actividades/"
    echo "   ├── project/"
    echo "   ├── setup-domain.sh"
    echo "   └── ..."
    exit 1
fi

# Verificar que el dominio apunte a este servidor
echo "📡 Verificando configuración DNS..."
IP=$(curl -s http://checkip.amazonaws.com)
echo "Tu IP pública es: $IP"
echo "Asegúrate de que $DOMAIN apunte a esta IP"

read -p "¿El DNS está configurado correctamente? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "❌ Configura el DNS primero y luego ejecuta este script nuevamente"
    echo "   En tu DNS agrega:"
    echo "   actividades.paloblancofreshfoods.com.gt. A $IP"
    exit 1
fi

# Crear directorios necesarios
echo "📁 Creando directorios..."
mkdir -p uploads database session_data logs certbot/conf certbot/www

# Dar permisos
chmod -R 755 uploads database session_data logs certbot

# Construir y ejecutar el contenedor
echo "🚀 Construyendo y ejecutando el contenedor..."
docker-compose down
docker-compose build --no-cache
docker-compose up -d

echo "⏳ Esperando que los servicios inicien..."
sleep 30

# Verificar que todo esté funcionando
if curl -f https://$DOMAIN/ > /dev/null 2>&1; then
    echo "✅ ✅ ✅ Configuración completada exitosamente!"
    echo "🌐 Accede a: https://$DOMAIN"
    echo ""
    echo "📊 Para ver los logs: docker-compose logs -f"
    echo "🛑 Para detener: docker-compose down"
else
    echo "⚠️  El dominio no responde aún. Espera unos minutos y verifica:"
    echo "    https://$DOMAIN"
    echo ""
    echo "🔍 Revisa los logs: docker-compose logs -f"
fi