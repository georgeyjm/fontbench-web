import re
import json
from pathlib import Path
from functools import lru_cache
from typing import Literal

import pandas as pd

from app.config import CHARSET_FILES, DATA_DIR
from app.models import FontMetric


# Regex for matching Chinese characters
CHINESE_RE = re.compile(r'[⺀-⺙⺛-⻳⼀-⿕々〇〡-〩〸-〺〻㐀-䶵一-鿃豈-鶴侮-頻並-龎]', re.UNICODE)


@lru_cache(maxsize=32)
def get_allowed_chars(charset: str) -> frozenset[str]:
    '''Get allowed characters for a charset (cached).'''
    if charset == 'chinese':
        return frozenset()  # Empty set means use regex
    return frozenset(CHARSET_FILES[charset].read_text(encoding='utf-8').splitlines())


def load_metric_data(font_metric: FontMetric, charset: Literal['3500', '7000', 'chinese'] = '3500') -> pd.DataFrame | None:
    '''
    Load data for a specific metric from a JSONL file.
    This is a generic loader that can be extended for different metrics.
    '''
    data_path = DATA_DIR / font_metric.data_path
    if not (data_path.exists() and data_path.is_file()):
        return None

    if font_metric.metric.name == 'grayscale':
        assert data_path.suffix == '.jsonl'
        return load_grayscale_jsonl(data_path, charset=charset)


@lru_cache(maxsize=128)
def load_grayscale_jsonl(jsonl_file: Path, charset: Literal['3500', '7000', 'chinese'] = '3500', sort: bool = True) -> pd.DataFrame:
    '''
    Process a JSONL file and return grayscale data (cached).
    Returns a tuple for hashability.
    '''
    use_regex = charset == 'chinese'
    if not use_regex:
        allowed_chars = get_allowed_chars(charset)

    data = []
    with jsonl_file.open('r', encoding='utf-8') as f:
        for line in f:
            line_data = json.loads(line)
            char = line_data['string']
            if not char:
                continue

            # Filter by charset
            if use_regex:
                if not CHINESE_RE.match(char):
                    continue
            else:
                if char not in allowed_chars:
                    continue

            grayscales = line_data.get('grayscale', {})
            for master_name, value in grayscales.items():
                data.append({
                    'string': char,
                    'master': master_name,
                    'grayscale': value,
                })

    # Sort by grayscale if requested
    df = pd.DataFrame(data)
    if sort:
        df = df.sort_values(by='grayscale')

    return df
