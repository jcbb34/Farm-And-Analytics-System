// Shared, immutable disclosure-state helpers for both farm area views.
export const toggleExpandedGroup = (expanded, id) => ({ ...expanded, [String(id)]: !expanded[String(id)] });
export const areGroupsExpanded = (expanded, ids) => ids.length > 0 && ids.every(id => Boolean(expanded[String(id)]));
export const setGroupsExpanded = (expanded, ids, open) => ({
    ...expanded,
    ...Object.fromEntries(ids.map(id => [String(id), Boolean(open)])),
});
