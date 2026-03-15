"""
Django settings for codegaze project.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# =========================================================
# 基础路径
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载 .env 文件
load_dotenv(BASE_DIR / ".env")

# =========================================================
# 安全配置
# =========================================================
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "please-change-this-in-env")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

# =========================================================
# Application definition
# =========================================================
INSTALLED_APPS = [
    'admin_interface',  # 必须放在 django.contrib.admin 之前
    'colorfield',       # 依赖
    'django.contrib.admin',

    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # 第三方应用
    'django_extensions',

    # 本地应用
    'accounts.apps.AccountsConfig',
    'programming',
    'community',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'codegaze.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'codegaze.wsgi.application'

# =========================================================
# Database
# =========================================================
DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.mysql'),
        'NAME': os.getenv('DB_NAME', 'codegaze_db'),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        }
    }
}

# =========================================================
# Password validation
# =========================================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =========================================================
# Internationalization
# =========================================================
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

# =========================================================
# 登录跳转
# =========================================================
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "programming:problem_list"
LOGOUT_REDIRECT_URL = "accounts:login"

# =========================================================
# Static files (CSS, JavaScript, Images)
# =========================================================
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# =========================================================
# 媒体文件配置
# =========================================================
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# AI 监测截图 / 日志图片目录
MONITOR_LOG_SUBDIR = 'monitor_logs'
MONITOR_LOG_DIR = os.path.join(MEDIA_ROOT, MONITOR_LOG_SUBDIR)

# =========================================================
# Default primary key field type
# =========================================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =========================================================
# 上传大小限制
# =========================================================
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024      # 5MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024      # 5MB

# =========================================================
# 缓存配置
# =========================================================
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'codegaze-local-cache',
        'TIMEOUT': 300,
    }
}

# =========================================================
# AI 监测配置
# =========================================================
AI_MONITOR = {
    'DEFAULT_BACKEND': 'haar',
    'ENABLE_PROFILE_FACE': True,
    'ENABLE_RELAXED_PASS': True,
    'SAVE_MONITOR_LOG': False,
    'MAX_IMAGE_WIDTH': 960,

    'SMOOTHING': {
        'ENABLE': True,
        'WINDOW_SIZE': 5,
        'MIN_STABLE_FRAMES': 3,
    },

    'HAAR': {
        'FRONTAL_MODEL': 'haarcascade_frontalface_alt2.xml',
        'PROFILE_MODEL': 'haarcascade_profileface.xml',

        'PASS1': {
            'scaleFactor': 1.1,
            'minNeighbors': 4,
            'min_ratio': 0.08,
            'min_px': 40,
        },

        'PASS2': {
            'scaleFactor': 1.06,
            'minNeighbors': 3,
            'min_ratio': 0.05,
            'min_px': 28,
        },

        'PROFILE': {
            'scaleFactor': 1.1,
            'minNeighbors': 4,
            'min_ratio': 0.07,
            'min_px': 36,
        }
    },

    'MEDIAPIPE': {
        'MIN_DETECTION_CONFIDENCE': 0.5,
        'MODEL_SELECTION': 0,
    },

    'YOLO': {
        'MODEL_PATH': os.path.join(BASE_DIR, 'models', 'yolo_face.pt'),
        'CONFIDENCE_THRESHOLD': 0.35,
        'IOU_THRESHOLD': 0.45,
    },

    'STATUS_RULES': {
        'FACE_TOO_SMALL_RATIO': 0.03,
        'MULTI_FACE_THRESHOLD': 2,
        'NO_FACE_SECONDS': 3,
    }
}

# =========================================================
# 日志配置
# =========================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '[{levelname}] {asctime} {name}: {message}',
            'style': '{',
        },
        'verbose': {
            'format': '[{levelname}] {asctime} {name} | {module}:{lineno} | {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_programming': {
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'programming.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'programming': {
            'handlers': ['console', 'file_programming'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# =========================================================
# AI Assistant 配置
# =========================================================
AI_ASSISTANT_PROVIDER = os.getenv("AI_ASSISTANT_PROVIDER", "demo")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1")
AI_ASSISTANT_MODEL = os.getenv("AI_ASSISTANT_MODEL", "deepseek-ai/deepseek-v3.2")
AI_ASSISTANT_TIMEOUT = int(os.getenv("AI_ASSISTANT_TIMEOUT", "60"))