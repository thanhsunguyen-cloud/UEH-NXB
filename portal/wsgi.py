"""Cấu hình WSGI cho gunicorn (Cloud Run và máy chủ Linux UEH)."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal.settings.prod")

application = get_wsgi_application()
