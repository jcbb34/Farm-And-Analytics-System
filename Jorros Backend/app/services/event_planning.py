"""Record and location domains for manually planned dashboard work."""

CROP_EVENTS = {"Planting", "Fertilization", "Irrigation", "Watering", "Harvesting", "Pest Control", "Crop Growth Monitoring"}
LIVESTOCK_EVENTS = {"Livestock Health Check", "Livestock Feeding", "Vaccination", "Weight Monitoring"}
EQUIPMENT_CATEGORIES = {
    "equipment",
    "tools",
    "machinery",
    "machine",
    "machines",
    "farm equipment",
    "farm tools",
    "implements",
}
NON_CONSUMING_INVENTORY_PLANS = {"inventory_restock_plan", "equipment_maintenance_plan"}


def event_domain(category):
    if category in CROP_EVENTS:
        return "Crop"
    if category in LIVESTOCK_EVENTS:
        return "Livestock"
    if category == "Inventory Restocking":
        return "Inventory"
    if category == "Equipment Maintenance":
        return "Equipment"
    return "General"


def is_equipment_category(category):
    return str(category or "").strip().casefold() in EQUIPMENT_CATEGORIES
