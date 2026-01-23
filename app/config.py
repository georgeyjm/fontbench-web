from pathlib import Path

# Base directories
APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / 'data'

# Character sets
CHARS_DIR = DATA_DIR / 'chars'
CHARSET_FILES = {
    '3500': CHARS_DIR / '3500.txt',
    '7000': CHARS_DIR / '7000.txt',
}

# Precomputed data directories
GRAYSCALE_DIR = DATA_DIR / 'grayscale'
