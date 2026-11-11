#!/bin/bash
# Arranque del contenedor en producción: Gunicorn (Flask) + Nginx + certificado SSL.
#
#  1. Inicia Gunicorn y espera a que responda.
#  2. Si NO hay certificado: Nginx en modo temporal (solo HTTP) y lo pide a Let's Encrypt.
#  3. Con certificado: Nginx con HTTPS.
#  4. Revisa la renovación del certificado dos veces al día (vence cada 90 días).
#  5. Si Gunicorn o Nginx se caen, el contenedor termina y Docker lo reinicia.
set -u

DOMAIN="${DOMAIN:-actividades.paloblancofreshfoods.com.gt}"
EMAIL="${CERTBOT_EMAIL:-admin@paloblancofreshfoods.com.gt}"
CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
PLANTILLAS=/etc/nginx/plantillas
WEBROOT=/var/www/certbot

cd /app
mkdir -p uploads/{cena-gerentes,sesion-gerentes-rrhh,convivio,actividad-bananero} \
         database logs .flask_session "$WEBROOT"

# Activa una plantilla de Nginx con el dominio real
usar_config() {
    sed "s/__DOMAIN__/${DOMAIN}/g" "${PLANTILLAS}/$1" > /etc/nginx/conf.d/default.conf
    nginx -t -q
}

PIDS=()
terminar() {
    echo "🛑 Deteniendo..."
    kill -TERM "${PIDS[@]}" 2>/dev/null
    wait
    exit 0
}
trap terminar TERM INT

# ---------- 1. Gunicorn ----------
echo "🚀 Iniciando Gunicorn..."
gunicorn -b 127.0.0.1:3000 --workers "${GUNICORN_WORKERS:-3}" --timeout 180 app:app &
GUNICORN_PID=$!
PIDS+=("$GUNICORN_PID")

for i in $(seq 1 30); do
    if curl -s -o /dev/null http://127.0.0.1:3000/; then
        echo "✅ Gunicorn listo"
        break
    fi
    if ! kill -0 "$GUNICORN_PID" 2>/dev/null; then
        echo "❌ Gunicorn se detuvo al iniciar (revisa la conexión a MySQL y el archivo .env)"
        exit 1
    fi
    sleep 2
done

# ---------- 2 y 3. Nginx y certificado ----------
if [ -f "$CERT" ]; then
    echo "🔒 Certificado encontrado para ${DOMAIN}"
    usar_config https.conf || exit 1
    nginx -g 'daemon off;' &
    NGINX_PID=$!
else
    echo "📄 No hay certificado: Nginx temporal (HTTP) para validar ${DOMAIN}..."
    usar_config http.conf || exit 1
    nginx -g 'daemon off;' &
    NGINX_PID=$!
    sleep 2

    if certbot certonly --webroot -w "$WEBROOT" -d "$DOMAIN" \
            --email "$EMAIL" --agree-tos --no-eff-email --non-interactive; then
        echo "✅ Certificado obtenido"
        usar_config https.conf && nginx -s reload
    else
        echo "⚠️  No se pudo obtener el certificado. El sitio queda solo en HTTP (el login no funcionará)."
        echo "    Revisa que el DNS de ${DOMAIN} apunte a este servidor y que el firewall permita los puertos 80 y 443."
        echo "    Luego reintenta con: docker compose restart sorteo-app"
    fi
fi
PIDS+=("$NGINX_PID")

# ---------- 4. Renovación automática ----------
(
    while true; do
        sleep 12h
        certbot renew --quiet --deploy-hook "nginx -s reload"
    done
) &
PIDS+=("$!")

echo "🎯 Listo: https://${DOMAIN}"

# ---------- 5. Vigilar procesos ----------
# Si Gunicorn o Nginx terminan, salir para que Docker reinicie el contenedor
wait -n "$GUNICORN_PID" "$NGINX_PID"
echo "❌ Gunicorn o Nginx se detuvo; reiniciando el contenedor..."
kill -TERM "${PIDS[@]}" 2>/dev/null
exit 1
