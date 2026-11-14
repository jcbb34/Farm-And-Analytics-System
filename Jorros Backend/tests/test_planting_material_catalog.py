"""Inventory planting material input rules for every built-in crop variety."""
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from app.services.crop_planting_material_catalog import catalog_entries, material_method
from app.services.crop_planting_material import validate_material_tag


def make(crop, variety, kind, category, unit, count=1):
    return SimpleNamespace(planting_crop_reference=crop, planting_variety_reference=variety,
                           planting_material_kind=kind, planting_units_per_position=count,
                           category=category, unit=unit)


def test_every_default_variety_has_a_compatible_material_method():
    catalog = catalog_entries()
    assert len(catalog) == 12
    assert len({(x['crop_key'], x['variety_key']) for x in catalog}) == len(catalog)
    for row in catalog:
        kind = row['default_material_kind']
        method = material_method(row['crop_key'], row['variety_key'], kind)
        assert method is not None
        assert method['default_units_per_position'] == 1
        validate_material_tag(make(row['crop_key'], row['variety_key'], kind, method['category'], method['unit']), require_for_planting_category=True)


def test_incompatible_materials_and_untagged_seeds_are_rejected():
    with pytest.raises(HTTPException) as error:
        validate_material_tag(make('banana', 'lakatan', 'seed', 'Seeds', 'seeds'))
    assert error.value.status_code == 422
    with pytest.raises(HTTPException):
        validate_material_tag(make('basil', 'genovese', 'seed', 'Planting Material', 'seeds'))
    with pytest.raises(HTTPException):
        validate_material_tag(make('banana', 'unknown', 'sucker', 'Planting Material', 'suckers'))
    with pytest.raises(HTTPException):
        validate_material_tag(make(None, None, None, 'Seeds', 'seeds', None), require_for_planting_category=True)


def test_seed_sowing_quantity_requires_actual_stock_count():
    seed = material_method('basil', 'genovese', 'seed')
    assert seed['default_units_per_position'] is None
    validate_material_tag(make('basil', 'genovese', 'seed', 'Seeds', 'seeds', 3), require_for_planting_category=True)
    with pytest.raises(HTTPException):
        validate_material_tag(make('basil', 'genovese', 'seed', 'Seeds', 'seeds', 0), require_for_planting_category=True)
