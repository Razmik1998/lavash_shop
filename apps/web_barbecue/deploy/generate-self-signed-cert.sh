#!/bin/sh
# Generates a self-signed TLS cert so Nginx's HTTPS listener has
# something to serve immediately on a fresh EC2 instance (reachable
# only by public IP, no DNS name yet). Browsers will warn on it -- once
# a real domain points at the instance, replace deploy/certs/*.pem with
# a real certificate (e.g. via certbot) and reload nginx; no config
# change needed since the paths stay the same.
set -e

CERT_DIR="$(dirname "$0")/certs"
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/fullchain.pem" ] && [ -f "$CERT_DIR/privkey.pem" ]; then
    echo "Certs already exist in $CERT_DIR, skipping."
    exit 0
fi

CN="${1:-localhost}"

openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out "$CERT_DIR/fullchain.pem" \
    -subj "/CN=${CN}"

echo "Generated self-signed cert for CN=${CN} in $CERT_DIR"
