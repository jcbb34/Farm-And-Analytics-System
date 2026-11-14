// The API is the single source of truth for built-in crop/variety propagation
// methods; avoid duplicating compatibility rules in React components.
export function catalogCrops(items = []) {
    return [...new Map(items.map(item => [item.crop_key, item.crop_name])).entries()];
}

export function catalogVarieties(items = [], cropKey) {
    return [...new Map(items.filter(item => item.crop_key === cropKey)
        .map(item => [item.variety_key, item.variety_name])).entries()];
}

export function plantingMethod(items = [], cropKey, varietyKey, materialKind) {
    const entry = items.find(item => item.crop_key === cropKey && item.variety_key === varietyKey);
    return entry?.material_types?.find(method => method.kind === materialKind) || null;
}

export function plantingMethods(items = [], cropKey, varietyKey, category) {
    const entry = items.find(item => item.crop_key === cropKey && item.variety_key === varietyKey);
    return (entry?.material_types || []).filter(method => method.category === category);
}
