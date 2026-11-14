"""Built-in crop-and-variety planting material compatibility.

These are propagation *types*, not agronomic sowing rates. The number of
seeds per planting position must be confirmed from the actual method/lot.
Only entries belonging to the system's default crop catalog are offered.
"""
from functools import lru_cache
from pathlib import Path
import json

# Each kind maps to its Inventory category and counted stock unit. The first
# kind is the suggested default, not a claim that no other method can work.
_BUILT_IN_KINDS = {
    "coconut": ("seedling", "seed"),
    "banana": ("sucker", "plantlet"),
    "cassava": ("sett", "cutting"),
    "sweet-potato": ("cutting", "plantlet"),
    "taro": ("corm", "plantlet"),
    "basil": ("seedling", "seed"),
}
_KIND_STOCK = {
    "seed": ("Seeds", "seeds"),
    "seedling": ("Seedlings", "seedlings"),
    "sucker": ("Planting Material", "suckers"),
    "cutting": ("Planting Material", "cuttings"),
    "corm": ("Planting Material", "corms"),
    "sett": ("Planting Material", "pieces"),
    "plantlet": ("Planting Material", "pieces"),
}


@lru_cache(maxsize=1)
def catalog_entries():
    """Canonical crop-variety pairs from the existing built-in spacing data."""
    seen = set()
    output = []
    reference_file = Path(__file__).resolve().parents[2] / "reference_data" / "crop_spacing_profiles.json"
    for profile in json.loads(reference_file.read_text(encoding="utf-8"))["profiles"]:
        crop, variety = profile["crop_key"], profile["variety_key"]
        if (crop, variety) in seen or crop not in _BUILT_IN_KINDS:
            continue
        seen.add((crop, variety))
        methods = [
            {"kind": kind, "category": _KIND_STOCK[kind][0],
             "unit": _KIND_STOCK[kind][1],
             # A seed's sowing rate depends on germination and thinning.
             "default_units_per_position": None if kind == "seed" else 1}
            for kind in _BUILT_IN_KINDS[crop]
        ]
        output.append({
            "crop_key": crop, "crop_name": profile["crop_name"],
            "variety_key": variety, "variety_name": profile["variety_name"],
            "default_material_kind": methods[0]["kind"], "material_types": methods,
        })
    return output


def catalog_entry(crop_key, variety_key):
    return next((entry for entry in catalog_entries()
                 if entry["crop_key"] == crop_key and entry["variety_key"] == variety_key), None)


def material_method(crop_key, variety_key, kind):
    entry = catalog_entry(crop_key, variety_key)
    return next((method for method in entry["material_types"] if method["kind"] == kind), None) if entry else None
