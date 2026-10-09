#!/bin/sh
# Entrypoint for the web_barbecue container: applies migrations and
# collects static files on every start (idempotent), then hands off to
# Daphne. Fails fast (set -e) so a broken migration stops the container
# instead of serving with a stale schema.
#
# Runs under Daphne (ASGI) rather than Gunicorn (WSGI) so a single
# process serves both plain HTTP and the /ws/admin/orders/ WebSocket -
# Django's ASGI application handles ordinary HTTP requests fine, so
# there is no need for a second WSGI process alongside it.
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec daphne -b 0.0.0.0 -p 8000 web_barbecue.asgi:application
