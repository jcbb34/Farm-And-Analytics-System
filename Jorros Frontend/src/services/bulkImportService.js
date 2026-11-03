import { farmDateKey } from "../utils/farmCalendar.js";
const IMPORT_KEY = "joross-bulk-imports-v1";
const SHEETJS_URL = "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js";

function parseJson(value, fallback) {
    try {
        return value ? JSON.parse(value) : fallback;
    } catch {
        return fallback;
    }
}

function normalizeHeader(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, " ")
        .trim();
}

function normalizedRow(row) {
    return Object.entries(row || {}).reduce((result, [key, value]) => {
        result[normalizeHeader(key)] = value;
        return result;
    }, {});
}

function firstValue(row, names, fallback = "") {
    for (const name of names) {
        const value = row[normalizeHeader(name)];

        if (value !== undefined && value !== null && String(value).trim() !== "") {
            return value;
        }
    }

    return fallback;
}

function asNumber(value, fallback = 0) {
    const number = Number(
        String(value ?? "")
            .replace(/,/g, "")
            .replace(/[^0-9.-]/g, "")
    );

    return Number.isFinite(number) ? number : fallback;
}

function asDate(value) {
    if (!value) {
        return "";
    }

    if (value instanceof Date && !Number.isNaN(value.getTime())) {
        return farmDateKey(value);
    }

    const text = String(value).trim();

    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
        return text;
    }

    const parsed = new Date(text);

    if (!Number.isNaN(parsed.getTime())) {
        return farmDateKey(parsed);
    }

    return text;
}

function createNumericId() {
    return Date.now() + Math.floor(Math.random() * 100000);
}

function createCode(prefix, index) {
    const suffix = String(Date.now()).slice(-5);
    return `${prefix}-${suffix}${String(index + 1).padStart(2, "0")}`;
}

function normalizeCrop(row, index) {
    const item = normalizedRow(row);

    return {
        id: createNumericId() + index,
        name: String(firstValue(item, ["Crop Name", "Name", "Crop"], `Imported Crop ${index + 1}`)).trim(),
        variety: String(firstValue(item, ["Variety", "Crop Variety"], "Not specified")).trim(),
        field: String(firstValue(item, ["Field", "Field Location", "Location"], "Unassigned Field")).trim(),
        area: asNumber(firstValue(item, ["Area", "Area ha", "Area in Hectares", "Hectares"], 0)),
        growth: Math.min(100, Math.max(0, asNumber(firstValue(item, ["Growth", "Growth Percent", "Growth Percentage"], 0)))),
        status: String(firstValue(item, ["Status", "Crop Status"], "Planted")).trim(),
        plantingDate: asDate(firstValue(item, ["Planting Date", "Date Planted"])),
        estimatedHarvest: asDate(firstValue(item, ["Estimated Harvest", "Est Harvest", "Harvest Date"])),
        lastUpdate: asDate(firstValue(item, ["Last Update", "Updated Date"], farmDateKey())),
        fertilizer: String(firstValue(item, ["Fertilizer", "Fertilizer Used"], "Not recorded")).trim(),
        pesticide: String(firstValue(item, ["Pesticide", "Pesticide Used"], "Not recorded")).trim(),
        watering: String(firstValue(item, ["Watering", "Watering Schedule"], "As needed")).trim(),
        notes: String(firstValue(item, ["Notes", "Remarks"], "Imported from spreadsheet.")).trim(),
        pestDisease: null,
        imported: true,
    };
}

function normalizeLivestock(row, index) {
    const item = normalizedRow(row);
    const quantity = Math.max(1, asNumber(firstValue(item, ["Animal Count", "Count", "Quantity", "No of Animals"], 1), 1));

    return {
        id: createNumericId() + index,
        animalId: String(firstValue(item, ["Animal ID", "ID", "Record ID"], createCode("C", index))).trim(),
        recordName: String(firstValue(item, ["Record Name", "Name", "Batch Name"], `Imported Livestock ${index + 1}`)).trim(),
        type: String(firstValue(item, ["Animal Type", "Type", "Livestock Type"], "Pig")).trim(),
        breed: String(firstValue(item, ["Breed"], "Not specified")).trim(),
        quantity,
        sex: String(firstValue(item, ["Sex", "Gender"], "Mixed")).trim(),
        healthStatus: String(firstValue(item, ["Health Status", "Health"], "Healthy")).trim(),
        age: String(firstValue(item, ["Age"], "Not specified")).trim(),
        weight: asNumber(firstValue(item, ["Average Weight", "Weight", "Weight kg"], 0)),
        dateOfBirth: asDate(firstValue(item, ["Date of Birth", "Birth Date", "DOB"])),
        penLocation: String(firstValue(item, ["Pen Location", "Location", "Pen"], "Unassigned Pen")).trim(),
        lastCheckup: asDate(firstValue(item, ["Last Checkup", "Checkup Date"], farmDateKey())),
        vaccinationStatus: String(firstValue(item, ["Vaccination Status"], "Not recorded")).trim(),
        nextVaccination: asDate(firstValue(item, ["Next Vaccination", "Vaccination Due"])),
        growthStatus: String(firstValue(item, ["Growth Status", "Status"], "Growing")).trim(),
        dateAcquired: asDate(firstValue(item, ["Date Acquired", "Acquired Date"])),
        acquiredFrom: String(firstValue(item, ["Acquired From", "Supplier", "Source"], "Not specified")).trim(),
        feedingSchedule: [],
        vaccinations: [],
        healthRecords: [],
        imported: true,
    };
}

function normalizeInventory(row, index) {
    const item = normalizedRow(row);

    return {
        id: createNumericId() + index,
        itemCode: String(firstValue(item, ["Item Code", "Inventory Code", "Code"], createCode("INV", index))).trim(),
        name: String(firstValue(item, ["Item Name", "Name", "Product"], `Imported Item ${index + 1}`)).trim(),
        category: String(firstValue(item, ["Category"], "Other")).trim(),
        quantity: asNumber(firstValue(item, ["Quantity", "Stock", "Current Quantity"], 0)),
        unit: String(firstValue(item, ["Unit"], "pcs")).trim(),
        reorderLevel: asNumber(firstValue(item, ["Reorder Level", "Minimum Stock", "Min Stock"], 0)),
        cost: asNumber(firstValue(item, ["Cost", "Unit Cost"], 0)),
        price: asNumber(firstValue(item, ["Price", "Selling Price"], 0)),
        supplier: String(firstValue(item, ["Supplier", "Source"], "Not specified")).trim(),
        dateAcquired: asDate(firstValue(item, ["Date Acquired", "Delivery Date", "Date Received"])),
        expirationDate: asDate(firstValue(item, ["Expiration Date", "Expiry Date"])),
        location: String(firstValue(item, ["Storage Location", "Location"], "Warehouse")).trim(),
        description: String(firstValue(item, ["Description"], "Imported inventory record.")).trim(),
        notes: String(firstValue(item, ["Notes", "Remarks"], "")).trim(),
        stockHistory: [],
        imported: true,
    };
}

const NORMALIZERS = {
    Crop: normalizeCrop,
    Livestock: normalizeLivestock,
    Inventory: normalizeInventory,
};

export function getBulkImports(moduleName) {
    const data = parseJson(localStorage.getItem(IMPORT_KEY), {
        Crop: [],
        Livestock: [],
        Inventory: [],
    });

    return moduleName ? data[moduleName] || [] : data;
}

export function saveBulkImport(moduleName, rows) {
    if (!NORMALIZERS[moduleName]) {
        throw new Error("Unsupported import module.");
    }

    const normalized = rows
        .filter((row) => row && Object.values(row).some((value) => String(value ?? "").trim() !== ""))
        .map((row, index) => NORMALIZERS[moduleName](row, index));

    const current = getBulkImports();
    const next = {
        ...current,
        [moduleName]: [
            ...normalized,
            ...(current[moduleName] || []),
        ].slice(0, 1000),
    };

    localStorage.setItem(IMPORT_KEY, JSON.stringify(next));

    window.dispatchEvent(
        new CustomEvent("joross:bulk-import-updated", {
            detail: {
                module: moduleName,
                count: normalized.length,
            },
        })
    );

    return normalized;
}

export function clearBulkImports(moduleName) {
    const current = getBulkImports();
    const next = {
        ...current,
        [moduleName]: [],
    };

    localStorage.setItem(IMPORT_KEY, JSON.stringify(next));
    return next;
}

export function mergeImportedRecords(defaultRecords, moduleName) {
    const imported = getBulkImports(moduleName);

    if (!imported.length) {
        return defaultRecords;
    }

    const seen = new Set();
    const keyFor = (record) => {
        if (moduleName === "Crop") {
            return `${record.name}|${record.field}|${record.plantingDate}`.toLowerCase();
        }

        if (moduleName === "Livestock") {
            return String(record.animalId || record.recordName || record.id).toLowerCase();
        }

        return String(record.itemCode || record.name || record.id).toLowerCase();
    };

    return [...imported, ...defaultRecords].filter((record) => {
        const key = keyFor(record);

        if (seen.has(key)) {
            return false;
        }

        seen.add(key);
        return true;
    });
}

function parseCsvLine(line) {
    const result = [];
    let current = "";
    let quoted = false;

    for (let i = 0; i < line.length; i += 1) {
        const char = line[i];

        if (char === '"') {
            if (quoted && line[i + 1] === '"') {
                current += '"';
                i += 1;
            } else {
                quoted = !quoted;
            }
        } else if (char === "," && !quoted) {
            result.push(current);
            current = "";
        } else {
            current += char;
        }
    }

    result.push(current);
    return result;
}

export function parseCsv(text) {
    const lines = String(text || "")
        .replace(/^\uFEFF/, "")
        .split(/\r?\n/)
        .filter((line) => line.trim() !== "");

    if (lines.length < 2) {
        throw new Error("The CSV must contain a header row and at least one data row.");
    }

    const headers = parseCsvLine(lines[0]).map((header) => header.trim());

    return lines.slice(1).map((line) => {
        const values = parseCsvLine(line);

        return headers.reduce((row, header, index) => {
            row[header] = values[index] ?? "";
            return row;
        }, {});
    });
}

function loadSheetJs() {
    if (window.XLSX) {
        return Promise.resolve(window.XLSX);
    }

    return new Promise((resolve, reject) => {
        const existing = document.querySelector(`script[data-joross-sheetjs="true"]`);

        if (existing) {
            existing.addEventListener("load", () => resolve(window.XLSX), { once: true });
            existing.addEventListener("error", () => reject(new Error("Excel parser failed to load.")), { once: true });
            return;
        }

        const script = document.createElement("script");
        script.src = SHEETJS_URL;
        script.async = true;
        script.dataset.jorossSheetjs = "true";
        script.onload = () => resolve(window.XLSX);
        script.onerror = () => reject(new Error("Excel import requires internet access the first time so the spreadsheet parser can load. CSV import works without it."));
        document.head.appendChild(script);
    });
}

export async function parseTabularFile(file) {
    if (!file) {
        throw new Error("Choose a CSV or Excel file first.");
    }

    const extension = file.name.split(".").pop()?.toLowerCase();

    if (extension === "csv") {
        return parseCsv(await file.text());
    }

    if (extension === "xlsx" || extension === "xls") {
        const XLSX = await loadSheetJs();
        const buffer = await file.arrayBuffer();
        const workbook = XLSX.read(buffer, {
            type: "array",
            cellDates: true,
        });
        const firstSheet = workbook.Sheets[workbook.SheetNames[0]];

        return XLSX.utils.sheet_to_json(firstSheet, {
            defval: "",
            raw: false,
        });
    }

    throw new Error("Only .csv, .xlsx, and .xls files are supported.");
}

export function getTemplateCsv(moduleName) {
    const templates = {
        Crop: [
            "Crop Name,Variety,Field,Area in Hectares,Growth,Status,Planting Date,Estimated Harvest,Notes",
            "Yellow Corn,Hybrid Corn,Corn Field 1,5.2,0,Planted,2026-08-08,2026-12-15,Imported example",
        ],
        Livestock: [
            "Animal ID,Record Name,Animal Type,Breed,Animal Count,Sex,Health Status,Average Weight,Date of Birth,Pen Location,Last Checkup",
            "C-2001,Pig Batch 06,Pig,Native,10,Mixed,Healthy,35,2026-06-01,Pen 6,2026-08-08",
        ],
        Inventory: [
            "Item Code,Item Name,Category,Quantity,Unit,Reorder Level,Cost,Price,Supplier,Date Acquired,Expiration Date,Storage Location,Notes",
            "INV-2001,Urea Fertilizer,Fertilizer,40,bags,10,900,1050,Sample Supplier,2026-08-08,2027-08-08,Warehouse A,Imported example",
        ],
    };

    return (templates[moduleName] || templates.Crop).join("\n");
}

export function downloadTemplate(moduleName) {
    const blob = new Blob([getTemplateCsv(moduleName)], {
        type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `joross-${moduleName.toLowerCase()}-import-template.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
}

export { IMPORT_KEY };
