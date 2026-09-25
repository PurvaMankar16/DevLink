"""
ASGI config for DevLink (Connect) project.

Routes HTTP requests through Django and WebSocket connections through
Django Channels. Used by Daphne in production.
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Connect.settings.production')

from django.core.asgi import get_asgi_application  # noqa: E402

# Initialize Django ASGI application first so app registry is ready
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.auth import AuthMiddlewareStack  # noqa: E402

# Import routing modules after Django application is initialized
import opportunities.routing  # noqa: E402
import notifications.routing  # noqa: E402
import messages.routing  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(
            opportunities.routing.websocket_urlpatterns +
            notifications.routing.websocket_urlpatterns +
            messages.routing.websocket_urlpatterns
        )
    ),
})
