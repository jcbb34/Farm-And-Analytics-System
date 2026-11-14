"""Crop/variety reference and persistence contract checks without SQL Server."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "app" / "services" / "crop_readiness_profiles.py"
spec = importlib.util.spec_from_file_location("readiness_reference_test", SOURCE)
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)


def test_every_default_crop_and_variety_has_an_observation_reference():
    for crop, variety in (
        ("Coconut", "Tall"), ("Coconut", "Dwarf"),
        ("Banana", "Lakatan"), ("Banana", "Saba"), ("Banana", "Latundan"),
        ("Cassava", "Lakan 1"), ("Sweet Potato", "Sp20"), ("Sweet Potato", "NSIC Sp30"),
        ("Taro", "Morondon"), ("Taro", "Iniito/VG2"),
        ("Basil", "Genovese"), ("Basil", "Siam Queen"),
    ):
        profile = ref.readiness_profile(crop, variety)
        assert profile["reference_scope"] == "variety_recognized", (crop, variety, profile)
        assert len(profile["checks"]) >= 3
        assert len({item["id"] for item in profile["checks"]}) == len(profile["checks"])
        assert profile["version"] > 0


def test_unknown_variety_uses_general_guidance_not_false_agricultural_certainty():
    unknown = ref.readiness_profile("Unknown Crop", "Unlisted")
    assert unknown["reference_scope"] == "general_guidance"
    assert all(item["help"] for item in unknown["checks"])
    unknown_variety = ref.readiness_profile("Banana", "New experimental cultivar")
    assert unknown_variety["reference_scope"] == "crop_level_guidance"


def test_cassava_and_basil_have_different_harvest_observations():
    cassava = ref.readiness_profile("Cassava", "Lakan 1")
    basil = ref.readiness_profile("Basil", "Genovese")
    assert "sample_root" in {item["id"] for item in cassava["checks"]}
    assert "regrowth_plan" in {item["id"] for item in basil["checks"]}
