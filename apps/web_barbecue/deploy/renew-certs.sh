#!/bin/sh
# Renews the Let's Encrypt certificate obtained by init-letsencrypt.sh and
# reloads Nginx. Let's Encrypt certs are valid 90 days; `certbot renew`
# only actually renews when a cert is within 30 days of expiry, so this
# is safe to run frequently. Intended for cron, e.g.:
#   0 3 * * 1 cd /home/ec2-user/dark_factory_shop/apps/web_barbecue && ./deploy/renew-certs.sh >> /var/log/certbot-renew.log 2>&1
set -e

cd "$(dirname "$0")/.."

docker run --rm \
    -v "$PWD/deploy/certbot-conf:/etc/letsencrypt" \
    -v "$PWD/deploy/certbot-webroot:/var/www/certbot" \
    -v "$PWD/deploy/certs:/etc/nginx-certs" \
    certbot/certbot renew \
    --deploy-hook 'for d in /etc/letsencrypt/live/*/; do cp -L "$d/fullchain.pem" "$d/privkey.pem" /etc/nginx-certs/; done'

docker compose exec nginx nginx -s reload
