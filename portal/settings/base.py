"""Cấu hình nền tảng (M0 sở hữu — các module M1–M8 không được sửa trực tiếp)."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    STAFF_GOOGLE_DOMAIN=(str, "ueh.edu.vn"),
    BOOTSTRAP_ADMIN_EMAILS=(list, []),
    FILE_STORAGE_BACKEND=(str, "local"),
    MAX_FILE_MB=(int, 200),
    MAX_LIBRARY_FILE_MB=(int, 10),
    GDRIVE_SHARED_DRIVE_ID=(str, ""),
    GDRIVE_CREDENTIALS_FILE=(str, ""),
    DEFAULT_FROM_EMAIL=(str, "nxbkt@ueh.edu.vn"),
)

env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(env_file)

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-dev-key-override-in-env")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Bên thứ ba
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    # Module nội bộ (M0 sở hữu accounts + core)
    "apps.accounts.apps.AccountsConfig",
    "apps.core.apps.CoreConfig",
    "apps.documents_drive.apps.DocumentsDriveConfig",
    "apps.customer.apps.CustomerConfig",
    "apps.backoffice.apps.BackofficeConfig",
    "apps.reports.apps.ReportsConfig",
    "apps.finance.apps.FinanceConfig",
    "apps.public_site.apps.PublicSiteConfig",
    "apps.administration.apps.AdministrationConfig",
    "apps.notifications.apps.NotificationsConfig",
]

SITE_ID = 1

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "portal.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.portal_navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "portal.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://ueh_portal:ueh_portal@localhost:5432/ueh_portal",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = 60

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.CustomerPasswordBackend",
    "apps.accounts.backends.PortalAllauthBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Ngôn ngữ và múi giờ bắt buộc theo mục 3
LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))
FILE_STORAGE_BACKEND = env("FILE_STORAGE_BACKEND")
MAX_FILE_MB = env("MAX_FILE_MB")
# CR-001: file nhỏ không thuộc hồ sơ (biểu mẫu, ảnh công khai) lưu qua save_library_file()
MAX_LIBRARY_FILE_MB = env("MAX_LIBRARY_FILE_MB")
# CR-001: Google Drive (M1). Rỗng GDRIVE_CREDENTIALS_FILE = dùng Application Default Credentials
GDRIVE_SHARED_DRIVE_ID = env("GDRIVE_SHARED_DRIVE_ID")
GDRIVE_CREDENTIALS_FILE = env("GDRIVE_CREDENTIALS_FILE")
UPLOAD_CHUNK_SIZE_BYTES = 8 * 1024 * 1024  # 8 MiB (bội số của 256 KiB)
DATA_UPLOAD_MAX_MEMORY_SIZE = (
    12 * 1024 * 1024
)  # Giới hạn 1 chunk + header (an toàn < 32 MiB Cloud Run)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cấu hình django-allauth: đăng nhập bằng email, không dùng username
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_ADAPTER = "apps.accounts.adapters.PortalAccountAdapter"
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.PortalSocialAccountAdapter"
SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

STAFF_GOOGLE_DOMAIN = env("STAFF_GOOGLE_DOMAIN").lower()
BOOTSTRAP_ADMIN_EMAILS = [
    email.strip().lower() for email in env("BOOTSTRAP_ADMIN_EMAILS") if email.strip()
]

GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID", default="")
GOOGLE_OAUTH_CLIENT_SECRET = env("GOOGLE_OAUTH_CLIENT_SECRET", default="")

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "key": "",
        },
    }
}

LOGIN_URL = "/tai-khoan/dang-nhap/"
LOGIN_REDIRECT_URL = "/tai-khoan/dieu-huong/"
LOGOUT_REDIRECT_URL = "/tai-khoan/dang-nhap/"

# Email (môi trường phát triển trỏ tới Mailpit qua EMAIL_URL)
EMAIL_CONFIG = env.email_url("EMAIL_URL", default="consolemail://")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
