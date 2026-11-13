import { resourceFitsTask } from "../../src/views/TaskManagement/taskManagementUtils.js";
// Adapt existing in-memory fixture collections to the bounded display API.
// This never contacts a backend. Real filtering/paging is covered by HTTP tests
// in Jorros Backend/tests/test_data_display_pages.py.
const value = (row, snake, camel = snake) => row[snake] ?? row[camel];
const date = row => value(row, "activity_date", "date") || "";
const text = (row, fields) => fields.map(key => row[key] || "").join(" ").toLowerCase();
const collection = body => Array.isArray(body) ? body : body?.data || [];

function cropOverview(rows) {
    const active = rows.filter(row => !value(row, "is_archived", "isArchived"));
    const status_counts = {}, months = new Map(), byCrop = new Map();
    let totalYield = 0, area = 0, growth = 0;
    for (const row of active) {
        status_counts[row.status] = (status_counts[row.status] || 0) + 1;
        area += Number(row.area_hectares ?? row.area ?? 0); growth += Number(row.current_growth ?? row.growth ?? 0);
        const monthKey = String(row.estimated_harvest ?? row.estimatedHarvest ?? "").slice(0, 7);
        if (monthKey) { const entry = months.get(monthKey) || { monthKey, cropCount: 0, area: 0 }; entry.cropCount++; entry.area += Number(row.area_hectares ?? row.area ?? 0); months.set(monthKey, entry); }
        for (const record of row.yield_records || row.yieldRecords || []) {
            const amount = Number(record.quantity_kg ?? record.quantityKg ?? 0); totalYield += amount;
            const entry = byCrop.get(row.name) || { cropName: row.name, quantityKg: 0, records: 0 }; entry.quantityKg += amount; entry.records++; byCrop.set(row.name, entry);
        }
    }
    const yieldByCrop = [...byCrop.values()].sort((a, b) => b.quantityKg - a.quantityKg);
    return { total: active.length, active: active.filter(row => !["Harvested", "Failed"].includes(row.status)).length,
        harvested: status_counts.Harvested || 0, ready: status_counts["Ready for Harvest"] || 0, area, alerts: 0, status_counts,
        names: [...new Set(rows.map(row => row.name).filter(Boolean))], fields: [...new Set(rows.map(row => row.field).filter(Boolean))],
        analytics: { monthlyPrediction: [...months.values()], yieldByCrop,
            productivityStats: { totalYield, totalArea: area, averageGrowth: active.length ? growth / active.length : 0, averageSurvival: null,
                topYieldCrop: yieldByCrop[0]?.cropName || "No data", yieldPerHectare: area ? totalYield / area : 0 } },
        chart_records: active, recommendation_crops: active,
    };
}
function animalOverview(rows) {
    const active = rows.filter(row => !value(row, "is_archived", "isArchived"));
    const population = {}, feed = {}, health = { Healthy: 0, "At Risk": 0, Sick: 0, "Under Treatment": 0 };
    for (const row of active) {
        const kind = value(row, "animal_type", "type") || "Other", quantity = Number(row.quantity || 0);
        population[kind] = (population[kind] || 0) + quantity;
        feed[kind] = (feed[kind] || 0) + Number(row.daily_feed_kg ?? row.feedingSchedule?.dailyAmountKg ?? 0) * quantity;
        const status = value(row, "health_status", "healthStatus") || "Healthy";
        if (status in health) health[status] += quantity;
    }
    return { records: active.length, total: Object.values(population).reduce((a, b) => a + b, 0), healthy: health.Healthy,
        risk: health.Sick + health["At Risk"] + health["Under Treatment"], vaccination_due: 0, births: 0,
        types: Object.keys(population), pens: [...new Set(active.map(row => value(row, "pen_location", "penLocation")).filter(Boolean))],
        health_counts: health, chart_records: active,
        analytics: { population, age_groups: {}, planned_feed: feed, estimated_monthly_budget: 0 } };
}
function adapt(path, rows, q) {
    const offset = Number(q.get("offset") || 0), limit = Number(q.get("limit") || 25);
    let items = rows;
    const result = () => ({ items: items.slice(offset, offset + limit), total: items.length, offset, limit });
    if (path === "/production-sales/stock") {
        const kind = q.get("kind") || "Production";
        items = rows.filter(row => kind === "Inventory" ? Boolean(row.is_saleable ?? row.isSaleable) && Number(row.quantity) > 0 && !value(row, "is_archived", "isArchived") : kind === "Live Animal" ? Number(row.quantity) > 0 && !value(row, "is_archived", "isArchived") : Number(row.available_quantity ?? row.quantity) > 0 && row.track_sale_inventory !== false);
        items = items.map(row => ({ id: row.id, kind, source_type: row.source_type,
            name: row.source_name ?? row.record_name ?? row.recordName ?? row.name ?? "Test stock",
            code: row.source_code ?? row.animal_code ?? row.animalId ?? row.item_code ?? row.itemCode ?? "",
            product_type: row.output_type ?? row.animal_type ?? row.category ?? "",
            available_quantity: Number(row.available_quantity ?? row.quantity),
            unit: kind === "Live Animal" ? "head" : row.unit, suggested_price: row.price,
        }));
        if (q.get("search")) items = items.filter(row => text(row, ["name", "code", "product_type"]).includes(q.get("search").toLowerCase()));
        return result();
    }
    if (path.startsWith("/activities/calendar/")) {
        items = rows.filter(row => date(row) >= q.get("date_from") && date(row) <= q.get("date_to") && !value(row, "is_archived", "isArchived"));
        items.sort((a,b) => date(a).localeCompare(date(b)) || String(a.start_time ?? a.startTime ?? "").localeCompare(String(b.start_time ?? b.startTime ?? "")) || a.id-b.id);
        if (path.endsWith("/events")) return result();
        const days = new Map();
        for (const row of items) {
            const key = date(row), day = days.get(key) || { date: key, total: 0, items: [] };
            day.total++; if (day.items.length < 4) day.items.push(row); days.set(key, day);
        }
        return { days: [...days.values()], summary: { total: items.length,
            harvests: items.filter(row => row.category === "Harvesting").length,
            livestock: items.filter(row => String(row.category).includes("Livestock") || row.category === "Vaccination").length,
            completed: items.filter(row => row.status === "Completed").length } };
    }
    if (path === "/resource-usages/consumption-summary") {
        const entries = rows.filter(row => !value(row, "is_voided", "isVoided"));
        const totals = new Map();
        for (const row of entries) {
            const usage_type = value(row, "usage_type", "usageType"), key = `${usage_type}|${row.unit}`;
            const item = totals.get(key) || { usage_type, unit: row.unit, quantity: 0 };
            item.quantity += Number(row.quantity); totals.set(key, item);
        }
        return { rows: [...totals.values()], total: entries.length };
    }
    if (["/display/crops/overview", "/display/crops/summary"].includes(path)) return cropOverview(rows);
    if (path === "/display/crops/chart") return { items: rows };
    if (path === "/display/livestock/overview") return animalOverview(rows);
    if (path === "/display/livestock/chart") return { items: rows };
    if (path === "/display/crops") {
        const filter = q.get("status_filter") || "Active Crops";
        items = rows.filter(row => {
            const archived = Boolean(value(row, "is_archived", "isArchived"));
            if (filter === "Archived") return archived;
            if (filter === "All") return true;
            if (archived) return false;
            return filter === "Active Crops" ? !["Harvested", "Failed"].includes(row.status) : row.status === (filter === "Fully Harvested/Completed" ? "Harvested" : filter);
        });
        for (const [key, field] of [["crop_type", "name"], ["field", "field"]]) if (q.get(key) && q.get(key) !== "All") items = items.filter(row => row[field] === q.get(key));
        if (q.get("search")) items = items.filter(row => text(row, ["name", "variety", "field", "crop_code"]).includes(q.get("search").toLowerCase()));
        return { ...result(), overview: cropOverview(rows) };
    }
    if (path === "/display/crop-yields") {
        items = rows.flatMap(row => (row.yield_records || row.yieldRecords || []).map(record => ({ ...record, crop_name: row.name, field: row.field, area: row.area_hectares ?? row.area })));
        return result();
    }
    if (path === "/display/livestock") {
        items = rows.filter(row => !value(row, "is_archived", "isArchived"));
        if (q.get("search")) items = items.filter(row => text(row, ["animal_code", "record_name", "animal_type", "breed", "pen_location"]).includes(q.get("search").toLowerCase()));
        for (const [key, snake, camel] of [["animal_type", "animal_type", "type"], ["pen", "pen_location", "penLocation"], ["health_status", "health_status", "healthStatus"]]) if (q.get(key) && q.get(key) !== "All") items = items.filter(row => value(row, snake, camel) === q.get(key));
        return { ...result(), overview: animalOverview(rows) };
    }
    if (path === "/display/livestock/records") {
        items = q.get("kind") === "feeding" ? rows.map(row => ({ ...row, livestock_id: row.id })) : rows.flatMap(row => (row.vaccination_records || row.vaccinationRecords || []).map(record => ({ ...record, record_name: row.record_name ?? row.recordName, animal_code: row.animal_code ?? row.animalId })));
        return result();
    }
    if (path === "/activities/summary") return { tasks_today: rows.filter(row => date(row) === q.get("activity_date") && ["Pending", "In Progress"].includes(row.status)).length };
    items = rows.filter(row => date(row) >= q.get("date_from") && date(row) <= q.get("date_to") && (q.get("view") === "upcoming" ? row.status === "Pending" : ["In Progress", "Completed"].includes(row.status)));
    const categories = [...new Set(items.map(row => row.category).filter(Boolean))], locations = [...new Set(items.map(row => row.location).filter(Boolean))];
    if (q.get("search")) items = items.filter(row => text(row, ["name", "related_to", "relatedTo", "location", "category", "description"]).includes(q.get("search").toLowerCase()));
    for (const [key, field] of [["category_filter", "category"], ["location_filter", "location"], ["status_filter", "status"]]) if (q.get(key) && q.get(key) !== "All") items = items.filter(row => row[field] === q.get(key));
    if (q.get("date_filter")) items = items.filter(row => date(row) === q.get("date_filter"));
    items.sort((a, b) => q.get("sort") === "A - Z" ? a.name.localeCompare(b.name) : q.get("sort") === "Z - A" ? b.name.localeCompare(a.name) : q.get("view") === "upcoming" || q.get("sort") === "Oldest" ? date(a).localeCompare(date(b)) : date(b).localeCompare(date(a)));
    return { ...result(), categories, locations };
}

export function withDisplayData(handler) {
    return async route => {
        // Legacy synthetic resource fixtures model an initial persisted version.
        const pathname = new URL(route.request().url()).pathname;
        if (/^\/api\/v1\/(?:crops|livestock|inventory)(?:\/(?:\d+|details))?$/.test(pathname) || /^\/api\/v1\/display\/(?:crops|livestock)$/.test(pathname)) {
            const target = route;
            const tag = row => row && typeof row === "object" && row.id != null ? { ...row, edit_version: row.edit_version ?? row.editVersion ?? 1 } : row;
            const versioned = body => Array.isArray(body) ? body.map(tag) : body?.items ? { ...body, items: body.items.map(tag) } : body?.data ? { ...body, data: versioned(body.data) } : tag(body);
            route = new Proxy(target, { get: (object, key) => key === "fulfill" ? async options => {
                if ((options.status || 200) >= 400) return object.fulfill(options);
                let body = options.json;
                if (!body && options.body) { try { body = JSON.parse(options.body); } catch { return object.fulfill(options); } }
                return body ? object.fulfill({ ...options, body: undefined, json: versioned(body) }) : object.fulfill(options);
            } : typeof object[key] === "function" ? object[key].bind(object) : object[key] });
        }
        const request = route.request(), url = new URL(request.url()), path = url.pathname.replace(/^\/api\/v1/, "");
        if (/^\/reports\/\d+\/pdf-job$/.test(path) && request.method() === "POST")
            return route.fulfill({ json: { report_id: Number(path.split("/")[2]), status: "Ready", attempts: 1, error: null } });
        const legacyPath = path === "/inventory/choices" ? "/inventory" : path === "/activities/resource-choices" ? "/activities/event-resources" : path === "/reports/pdf-jobs/status" ? "/reports" : path === "/production-sales/stock" ? (url.searchParams.get("kind") === "Inventory" ? "/inventory" : url.searchParams.get("kind") === "Live Animal" ? "/livestock" : "/production-sales/production") : path.startsWith("/activities/calendar/") ? "/activities" : path.startsWith("/display/crop") ? "/crops/details" : path.startsWith("/display/livestock") ? "/livestock" : ["/activities/page", "/activities/summary"].includes(path) ? "/activities" : path === "/resource-usages/consumption-summary" ? "/resource-usages" : null;
        if (!legacyPath) return handler(route);
        const fixtureUrl = new URL(url); fixtureUrl.pathname = `/api/v1${legacyPath}`;
        if (path === "/production-sales/stock" && (url.searchParams.get("kind") || "Production") === "Production") fixtureUrl.searchParams.set("available_only", "true");
        const proxyRequest = new Proxy(request, { get: (target, key) => key === "url" ? () => fixtureUrl.toString() : typeof target[key] === "function" ? target[key].bind(target) : target[key] });
        const proxyRoute = new Proxy(route, { get: (target, key) => key === "request" ? () => proxyRequest : key === "fulfill" ? async options => {
            if ((options.status || 200) >= 400) return target.fulfill(options);
            const body = options.json ?? (options.body ? JSON.parse(options.body) : []);
            if ((Array.isArray(body?.items) && Number.isInteger(body.total)) || (Array.isArray(body?.days) && body.summary) || (path === "/display/crops/summary" && body?.analytics && Number.isInteger(body.total))) return target.fulfill(options);
            if (path === "/activities/resource-choices" || path === "/inventory/choices") {
                const domain = path === "/inventory/choices" ? "Inventory" : url.searchParams.get("domain"), selectedId = Number(url.searchParams.get("selected_id"));
                let rows = (path === "/inventory/choices" ? collection(body) : body[domain === "Crop" ? "crops" : domain === "Livestock" ? "livestock" : "inventory"] || []).map(row => ({
                    ...row, name: row.name ?? row.record_name ?? row.recordName,
                    code: row.code ?? row.crop_code ?? row.cropCode ?? row.animal_code ?? row.animalId ?? row.item_code ?? row.itemCode,
                    cropCode: row.cropCode ?? row.code ?? row.crop_code,
                    recordName: row.recordName ?? row.name ?? row.record_name,
                    animalId: row.animalId ?? row.code ?? row.animal_code,
                    penLocation: row.penLocation ?? row.location ?? row.pen_location,
                    itemCode: row.itemCode ?? row.code ?? row.item_code,
                    expirationDate: row.expirationDate ?? row.expiration_date,
                })).filter(row => !value(row, "is_archived", "isArchived"));
                const work = url.searchParams.get("work_module"), kind = url.searchParams.get("work_kind");
                if (domain === "Inventory" && work) rows = rows.filter(row => resourceFitsTask(row, work, kind === "all" ? "" : kind));
                const selected = rows.find(row => row.id === selectedId) || null;
                const search = (url.searchParams.get("search") || "").toLowerCase();
                rows = rows.filter(row => text(row, ["name", "code", "field", "location", "penLocation", "category"]).includes(search));
                const offset = Number(url.searchParams.get("offset") || 0), limit = Number(url.searchParams.get("limit") || 25);
                return target.fulfill({ ...options, body: undefined, json: { items: rows.slice(offset, offset + limit), selected, total: rows.length, offset, limit } });
            }
            if (path === "/reports/pdf-jobs/status") {
                const ids = new Set((url.searchParams.get("report_ids") || "").split(",").map(Number));
                return target.fulfill({ ...options, body: undefined, json: collection(body).filter(row => ids.has(row.id)).map(row => ({ report_id: row.id, status: "Ready", error: null })) });
            }
            return target.fulfill({ ...options, body: undefined, json: adapt(path, collection(body), url.searchParams) });
        } : typeof target[key] === "function" ? target[key].bind(target) : target[key] });
        return handler(proxyRoute);
    };
}
