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

# ¿El dominio apunta a este servidor? Así no se gastan intentos de Let's Encrypt
# (máximo 5 fallidos por hora) mientras el DNS no esté listo.
dns_listo() {
    local ip_publica resueltas
    ip_publica=$(curl -sf -m 5 -H "Metadata-Flavor: Google" \
        http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip \
        || curl -sf -m 5 https://checkip.amazonaws.com || true)
    resueltas=$(getent ahosts "$DOMAIN" | awk '{print $1}' | sort -u | tr '\n' ' ')
    if [ -z "$ip_publica" ]; then
        return 0  # No se pudo averiguar la IP pública: se intenta de todas formas
    fi
    if [ "$resueltas" = "$ip_publica " ]; then
        return 0
    fi
    echo "⏸️  ${DOMAIN} resuelve a: ${resueltas:-nada}; este servidor es ${ip_publica}."
    echo "    Debe resolver SOLO a ${ip_publica} (sin proxy de Cloudflare ni IPv6). Se reintentará en 10 minutos."
    return 1
}

# Pide el certificado y, si lo obtiene, activa HTTPS sin reiniciar
pedir_certificado() {
    dns_listo || return 1
    if certbot certonly --webroot -w "$WEBROOT" -d "$DOMAIN" \
            --email "$EMAIL" --agree-tos --no-eff-email --non-interactive; then
        echo "✅ Certificado obtenido"
        usar_config https.conf && nginx -s reload && echo "🔒 HTTPS activo: https://${DOMAIN}"
        return 0
    fi
    echo "⚠️  Let's Encrypt rechazó la validación. Se reintentará en 10 minutos."
    return 1
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
    pedir_certificado || echo "    Mientras tanto el sitio funciona solo en HTTP (el login requiere HTTPS)."
fi
PIDS+=("$NGINX_PID")

# ---------- 4. Certificado pendiente y renovación automática ----------
(
    # Sin certificado: reintenta cada 10 minutos (solo pide si el DNS ya apunta aquí)
    while [ ! -f "$CERT" ]; do
        sleep 10m
        pedir_certificado
    done
    while true; do
        sleep 12h
        certbot renew --quiet --deploy-hook "nginx -s reload"
    done
) &
PIDS+=("$!")

if [ -f "$CERT" ]; then
    echo "🎯 Listo: https://${DOMAIN}"
else
    echo "🎯 Listo (por ahora solo HTTP): http://${DOMAIN}"
fi

# ---------- 5. Vigilar procesos ----------
# Si Gunicorn o Nginx terminan, salir para que Docker reinicie el contenedor
wait -n "$GUNICORN_PID" "$NGINX_PID"
echo "❌ Gunicorn o Nginx se detuvo; reiniciando el contenedor..."
kill -TERM "${PIDS[@]}" 2>/dev/null
exit 1
