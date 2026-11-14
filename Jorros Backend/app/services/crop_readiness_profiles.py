"""Versioned, observation-based harvest readiness reference for Joross Farm.

These are inspection prompts, not automatic proof of harvest maturity. A farm
worker confirms observations for the selected planting and the administrator
can review the recorded results. All values are recommendations, not measurements.
"""
from __future__ import annotations

import re

PROFILE_VERSION = 1


def _slug(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


# Each check describes something the inspector can physically verify, even if
# planting age or flowering dates are unknown (common for existing plants).
BASE = {
    "coconut": {
        "label": "Coconut fruit maturity inspection",
        "checks": [
            ("mature_bunch", "Fruit bunch is appropriate for the intended product", "Check fruit age if known and inspect the bunch; buko and mature coconuts have different harvesting stages."),
            ("fruit_quality", "Sampled fruits meet the farm's maturity and quality criteria", "Check fruit development and condition, not just the expected harvest date."),
            ("safe_harvest", "Harvesting is safe and the trees are healthy enough for the planned work", "Check falling-fruit hazards, access, workers, and tree condition."),
        ],
        "source": "Philippine coconut production guidance; field inspection required",
        "note": "Tall and Dwarf are perennial. Harvest removes fruits, not the coconut tree. Match maturity to product purpose.",
    },
    "banana": {
        "label": "Banana bunch maturity inspection",
        "checks": [
            ("bunch_development", "Bunch and fingers show suitable fullness for harvest", "Check reduced angularity and fullness of representative fingers."),
            ("bunch_condition", "Fruit is sound and shows the required maturity for its market", "Inspect fruit development, damage, and disease; confirm target market."),
            ("harvest_plan", "The correct bunch and pseudostem were identified", "Only the producing pseudostem finishes after bunch harvest; successor suckers may remain."),
        ],
        "source": "Philippine Department of Agriculture banana production manual",
        "note": "Use the shooting date if known, but do not estimate fruit maturity from planting date alone.",
    },
    "cassava": {
        "label": "Cassava root harvest inspection",
        "checks": [
            ("sample_root", "Representative sample roots meet expected size and condition", "Inspect roots from a representative plant; calendar age alone is not enough."),
            ("root_quality", "Sample roots are suitable for the planned use", "Check damage, rot, and quality relative to intended use."),
            ("end_of_crop", "Harvesting method and affected plants are identified", "Root harvest normally ends the harvested plant's growing cycle."),
        ],
        "source": "PhilRootcrops root crop production references",
        "note": "Root sampling is needed before confirmation, particularly when planting age is uncertain.",
    },
    "sweetpotato": {
        "label": "Sweet potato storage-root inspection",
        "checks": [
            ("root_sample", "Sample storage roots have acceptable size", "Dig a small representative sample to inspect root size and maturity."),
            ("root_health", "Sample roots meet quality and pest-condition requirements", "Inspect for cracking, disease, and insect damage."),
            ("harvest_scope", "Root harvest area and plant-removal plan are confirmed", "Root harvest normally ends that planting; leaf harvesting is a different operation."),
        ],
        "source": "PhilRootcrops / Visayas State University sweet potato guidance",
        "note": "PSB Sp20 and NSIC Sp30 estimates must be checked against sampled storage roots.",
    },
    "taro": {
        "label": "Taro (gabi) corm inspection",
        "checks": [
            ("sample_corm", "Sample corm size supports harvesting", "Check a representative corm; maturity differs with variety and local conditions."),
            ("plant_condition", "Plant condition was assessed alongside weather and disease", "Leaf yellowing can reflect stress, not only harvest maturity."),
            ("harvest_scope", "Corm or leaf harvest has been clearly identified", "Corm harvesting ends affected planting; selective leaf harvesting is a separate activity."),
        ],
        "source": "Philippine gabi production guidance (variety-specific timing may be unverified)",
        "note": "For Morondon and Iniito/VG2, require physical corm inspection rather than fixed maturity dates.",
    },
    "basil": {
        "label": "Basil cutting and regrowth inspection",
        "checks": [
            ("leaf_growth", "There are sufficient healthy leaves for a partial cutting", "Inspect actual vegetative growth and usable leaf quality."),
            ("plant_health", "Plants show no condition requiring harvest postponement", "Inspect for disease, pests, stress, and undesirable flowering."),
            ("regrowth_plan", "Enough healthy nodes and foliage will remain for regrowth", "Do not cut the plant so severely that repeated harvest becomes impossible."),
        ],
        "source": "University extension basil harvest and pruning guidance",
        "note": "Genovese and Siam Queen are repeated-cutting herbs; harvest timing varies by growth and conditions.",
    },
}

VARIETIES = {
    "coconut": {"tall": "Tall", "dwarf": "Dwarf"},
    "banana": {"lakatan": "Lakatan", "saba": "Saba", "latundan": "Latundan"},
    "cassava": {"lakan1": "Lakan 1"},
    "sweetpotato": {"sp20": "PSB Sp20", "psbsp20": "PSB Sp20", "nsicsp20": "PSB Sp20", "sp30": "NSIC Sp30", "nsicsp30": "NSIC Sp30"},
    "taro": {"iniito": "Iniito / VG2", "vg2": "Iniito / VG2", "iniitovg2": "Iniito / VG2", "morondon": "Morondon"},
    "basil": {"genovese": "Genovese", "siamqueen": "Siam Queen", "queen": "Siam Queen"},
}


def readiness_profile(crop_name: str, variety: str) -> dict:
    name = _slug(crop_name)
    if name in {"kamote", "sweetpotatoes"}: name = "sweetpotato"
    if name in {"gabi"}: name = "taro"
    ref = BASE.get(name)
    variety_key = _slug(variety)
    known = VARIETIES.get(name, {}).get(variety_key)
    if not ref:
        return {
            "key": "general", "version": PROFILE_VERSION,
            "crop": crop_name, "variety": variety,
            "title": "General crop readiness inspection",
            "reference_scope": "general_guidance",
            "source": "General crop inspection; variety-specific reference not yet available",
            "guidance": "Verify physical maturity and suitability before changing a crop to Ready for Harvest.",
            "checks": [
                {"id": "maturity", "label": "Actual harvestable product shows appropriate maturity", "help": "Inspect the produce, not only its projected harvest date."},
                {"id": "condition", "label": "Crop and produce condition are suitable for harvest", "help": "Check for disease, damage, or stress."},
                {"id": "harvest_scope", "label": "Harvest type, location, and affected plants are verified", "help": "Confirm whether this is partial or final harvesting."},
            ],
        }
    return {
        "key": name, "version": PROFILE_VERSION,
        "crop": crop_name,
        "variety": known or variety,
        "title": ref["label"],
        "reference_scope": "variety_recognized" if known else "crop_level_guidance",
        "source": ref["source"],
        "guidance": ref["note"],
        "checks": [{"id": code, "label": label, "help": help_text} for code, label, help_text in ref["checks"]],
    }
