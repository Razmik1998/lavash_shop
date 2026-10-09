#!/bin/sh
# One-time: obtains a real, browser-trusted TLS certificate from Let's
# Encrypt for this EC2 instance's public DNS name and installs it where
# Nginx already expects it (deploy/certs/*.pem), replacing the
# self-signed bootstrap cert. Nginx must already be running and
# reachable on port 80 from the internet (the HTTP-01 challenge proves
# domain ownership by fetching a file over plain HTTP).
#
# Usage: ./deploy/init-letsencrypt.sh <domain> <email>
# Example: ./deploy/init-letsencrypt.sh \
#            ec2-13-53-127-102.eu-north-1.compute.amazonaws.com you@example.com
set -e

DOMAIN="${1:?Usage: $0 <domain> <email>}"
EMAIL="${2:?Usage: $0 <domain> <email>}"

cd "$(dirname "$0")/.."

mkdir -p deploy/certbot-webroot deploy/certbot-conf deploy/certs

docker run --rm \
    -v "$PWD/deploy/certbot-conf:/etc/letsencrypt" \
    -v "$PWD/deploy/certbot-webroot:/var/www/certbot" \
    -v "$PWD/deploy/certs:/etc/nginx-certs" \
    certbot/certbot certonly \
    --webroot -w /var/www/certbot \
    -d "$DOMAIN" \
    --email "$EMAIL" --agree-tos --no-eff-email \
    --deploy-hook "cp -L /etc/letsencrypt/live/$DOMAIN/fullchain.pem /etc/letsencrypt/live/$DOMAIN/privkey.pem /etc/nginx-certs/"

echo "Reloading nginx with the new certificate..."
docker compose exec nginx nginx -s reload

echo "Done. https://$DOMAIN should now show a trusted certificate."
echo "Set up renewal: crontab -e, then add a weekly call to deploy/renew-certs.sh"
