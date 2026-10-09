"""ASGI entrypoint serving both HTTP and the /ws/admin/orders/ WebSocket.

Per task-plan.md's decision, the whole app runs under one ASGI process
(daphne) instead of splitting HTTP (gunicorn) and WebSocket (a second
process) - Django's ASGI application already serves plain HTTP fine, so
there is no reason to run two server processes.

The WebSocket route is not wrapped in AuthMiddlewareStack: this app has
no session/cookie-based auth for machine-to-machine traffic (see
products/auth.py), so authentication is done inside
orders.consumers.AdminOrdersConsumer.connect() against the same
X-API-Key header convention used by the HTTP endpoints.
"""
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_barbecue.settings")

# get_asgi_application() must be called before importing anything that
# imports models (orders.routing -> orders.consumers -> orders.models),
# so Django's app registry is populated first.
django_asgi_app = get_asgi_application()

from orders.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
