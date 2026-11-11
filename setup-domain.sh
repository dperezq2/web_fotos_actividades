#!/bin/bash
# Instalación desde cero en el servidor (Debian/Ubuntu, p. ej. una VM de Google Cloud).
# Se puede ejecutar de nuevo sin problema: lo que ya está hecho se omite.
#
#   cd web_fotos_actividades
#   bash setup-domain.sh
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d project ] || [ ! -f docker-compose.yml ]; then
    echo "❌ Ejecuta este script desde la carpeta del proyecto (donde está docker-compose.yml)."
    exit 1
fi

preguntar() {  # preguntar "texto" -> 0 si responde s/y
    local r
    read -r -p "$1 (s/n): " r
    [[ "$r" =~ ^[SsYy]$ ]]
}

# ---------- 1. Docker ----------
if ! command -v docker >/dev/null 2>&1; then
    echo "🐳 Docker no está instalado."
    preguntar "¿Instalarlo ahora con el instalador oficial (get.docker.com)?" || exit 1
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    echo "✅ Docker instalado. (Desde tu próxima sesión SSH podrás usar 'docker' sin sudo.)"
fi

DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
    DOCKER="sudo docker"  # El grupo 'docker' aún no aplica en esta sesión
fi

if ! $DOCKER compose version >/dev/null 2>&1; then
    echo "❌ Falta el plugin 'docker compose'. Instálalo con: sudo apt-get install -y docker-compose-plugin"
    exit 1
fi

# ---------- 2. Archivo .env ----------
if [ ! -f .env ]; then
    echo "🔑 Creando .env con contraseñas aleatorias..."
    cp .env.example .env
    sed -i \
        -e "s/^MYSQL_ROOT_PASSWORD=.*/MYSQL_ROOT_PASSWORD=$(openssl rand -hex 16)/" \
        -e "s/^MYSQL_PASSWORD=.*/MYSQL_PASSWORD=$(openssl rand -hex 16)/" \
        -e "s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" \
        .env
    chmod 600 .env
    echo "✅ .env creado. Guarda una copia de ese archivo en un lugar seguro."
else
    echo "✅ .env ya existe (no se modifica)"
fi

# Lee DOMAIN y CERTBOT_EMAIL del .env
DOMAIN=$(grep -E '^DOMAIN=' .env | cut -d= -f2- || true)
DOMAIN=${DOMAIN:-actividades.paloblancofreshfoods.com.gt}

# ---------- 3. DNS ----------
echo "📡 Verificando DNS de ${DOMAIN}..."
IP_PUBLICA=$(curl -sf -m 5 -H "Metadata-Flavor: Google" \
    http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip \
    || curl -sf -m 5 https://checkip.amazonaws.com || true)
IP_DNS=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1 {print $1}' || true)
echo "   IP pública de este servidor: ${IP_PUBLICA:-desconocida}"
echo "   IP a la que apunta ${DOMAIN}: ${IP_DNS:-ninguna}"

if [ -z "$IP_DNS" ] || [ "$IP_DNS" != "$IP_PUBLICA" ]; then
    echo "⚠️  El dominio no apunta a este servidor. Crea en tu DNS el registro:"
    echo "      ${DOMAIN}.  A  ${IP_PUBLICA}"
    echo "   Sin eso no se puede obtener el certificado SSL."
    preguntar "¿Continuar de todas formas?" || exit 1
fi

# ---------- 4. Puertos 80 y 443 libres ----------
if command -v ss >/dev/null 2>&1; then
    OCUPADOS=$(sudo ss -ltnpH '( sport = :80 or sport = :443 )' | grep -v docker-proxy || true)
    if [ -n "$OCUPADOS" ]; then
        echo "⚠️  Otro programa usa el puerto 80 o 443 (p. ej. Apache o Nginx instalados en la VM):"
        echo "$OCUPADOS"
        echo "   Detenlo antes de continuar (p. ej.: sudo systemctl disable --now nginx apache2)."
        preguntar "¿Continuar de todas formas?" || exit 1
    fi
fi

# ---------- 5. Carpetas de datos (persisten aunque se reconstruya el contenedor) ----------
mkdir -p uploads database session_data logs certbot/conf certbot/www mysql/data

# ---------- 6. Construir e iniciar ----------
echo "🚀 Construyendo e iniciando (la primera vez tarda unos minutos)..."
$DOCKER compose up -d --build

echo "⏳ Esperando el arranque y el certificado SSL..."
for i in $(seq 1 60); do
    LOGS=$($DOCKER compose logs sorteo-app 2>&1 | tail -n 40)
    if grep -q "🎯 Listo" <<<"$LOGS"; then
        break
    fi
    sleep 3
done
$DOCKER compose logs sorteo-app 2>&1 | tail -n 15

echo
if curl -sf -o /dev/null -m 10 "https://${DOMAIN}/login"; then
    echo "✅ ✅ ✅ ¡Listo! https://${DOMAIN}"
else
    echo "⚠️  https://${DOMAIN} aún no responde. Revisa los mensajes de arriba o:"
    echo "      $DOCKER compose logs -f sorteo-app"
fi

cat <<EOF

Siguientes pasos:
  • Crear el primer SUPERADMIN (solo la primera vez):
      $DOCKER compose exec sorteo-app flask --app app crear-superadmin
  • Luego entra a https://${DOMAIN}/login e importa el CSV de empleados.
  • Fotos de actividades: https://${DOMAIN}/convivio (y las demás actividades).

Comandos útiles:
  • Actualizar tras un git pull:  $DOCKER compose up -d --build sorteo-app
  • Ver logs:                     $DOCKER compose logs -f sorteo-app
  • Detener todo:                 $DOCKER compose down
EOF
