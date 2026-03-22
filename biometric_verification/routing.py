"""
WebSocket URL routing for biometric verification module.

This file is auto-discovered by openIMIS/asgi.py.
All patterns defined in websocket_urlpatterns will be registered
in the global ASGI WebSocket router.
"""

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^api/ws/biometric/verify/$', consumers.BiometricVerificationConsumer.as_asgi()),
]
