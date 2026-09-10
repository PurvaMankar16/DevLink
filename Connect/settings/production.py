"""
Production settings for DevLink.
"""

from .base import *  # noqa: F401, F403
import environ

env = environ.Env()

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
DEBUG = env.bool('DEBUG', default=False)

# ---------------------------------------------------------------------------
# Database — PostgreSQL via DATABASE_URL with SQLite fallback
# ---------------------------------------------------------------------------
DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}

# ---------------------------------------------------------------------------
# Channels — Redis channel layer with InMemory fallback
# ---------------------------------------------------------------------------
REDIS_URL = env('REDIS_URL', default=None)

if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [REDIS_URL],
                'capacity': 1500,
                'expiry': 10,
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# ---------------------------------------------------------------------------
# Celery — Broker & Backend using REDIS_URL if available
# ---------------------------------------------------------------------------
if REDIS_URL:
    CELERY_BROKER_URL = env('CELERY_BROKER_URL', default=REDIS_URL)
    CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default=REDIS_URL)

# ---------------------------------------------------------------------------
# Email — Console backend fallback if no SMTP configured
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=False)
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=False)

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_ROOT = BASE_DIR / 'staticfiles'  # noqa: F405
