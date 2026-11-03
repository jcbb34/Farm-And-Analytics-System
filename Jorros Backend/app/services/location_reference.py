"""Offline PSA-derived address choices; custom entries remain in personal records."""
from functools import lru_cache
import json
from pathlib import Path

@lru_cache(maxsize=1)
def catalogue():
    return json.loads((Path(__file__).resolve().parents[2] / 'reference_data/philippine_locations.json').read_text(encoding='utf-8'))

@lru_cache(maxsize=3)
def location_index(level):
    return {row['code']: row for row in catalogue()[level]}

def choices(level, parent_code=None):
    parent = {'cities': 'province_code', 'barangays': 'city_code'}.get(level)
    return sorted(({'code': row['code'], 'name': row['name']} for row in catalogue()[level]
                   if parent is None or row[parent] == parent_code), key=lambda row: row['name'])
