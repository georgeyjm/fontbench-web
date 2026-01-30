from pathlib import Path

# Base directories
APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / 'static'
DATA_DIR = APP_DIR / 'data'
UPLOADS_DIR = APP_DIR / 'uploads'

# Database
DATABASE_PATH = APP_DIR / 'fontbench.db'

# Character sets
CHARS_DIR = DATA_DIR / 'chars'
CHARSET_FILES = {
    '3500': CHARS_DIR / '3500.txt',
    '7000': CHARS_DIR / '7000.txt',
}

# Available processing metrics
AVAILABLE_METRICS = [
    {
        'name': 'grayscale',
        'display_name': '灰度',
        'description': '字符的黑色像素比值',
    },
]

# Ensure directories exist
STATIC_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
