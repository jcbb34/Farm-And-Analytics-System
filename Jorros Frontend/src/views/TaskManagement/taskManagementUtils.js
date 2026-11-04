import { emptyPersonalDetails } from "../../components/PersonalDetails/personalDetails.js";
import { farmDateKey } from "../../utils/farmCalendar.js";
import { makeWeeklySchedule } from "../../components/WeeklyScheduleEditor/weeklySchedule.js";

const today = () => farmDateKey();
const addDaysToDateKey = (key, days) => {
    const [year, month, day] = String(key).split("-").map(Number);
    const value = new Date(year, month - 1, day);
    value.setDate(value.getDate() + days);
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
};
const EMPTY_TASK = {
    name: "", category: "General", related_to: "General Farm", location: "Jorros Farm",
    description: "", instructions: "", activity_date: today(), start_time: "08:00",
    employee_id: "", priority: "Medium", requires_review: true, requires_evidence: true,
    feeding_slot: "", backup_employee_id: "", time_sensitive: false, controlled_rescheduling: false, max_delay_minutes: "",
    planned_quantity: "", planned_unit: "",
    planned_inventory_item_id: "", planned_usage_type: "",
    source_module: "", source_type: "manual_work", source_record_id: "", source_path: "",
};

const EMPTY_ASSISTED_SUBMISSION = {
    employee_id: "", inventory_item_id: "", actual_quantity: "", actual_unit: "", actual_quantity_confirmed: false, evidence_url: "",
    harvest_type_intent: "",
    worker_notes: "", problem_report: "", assisted_reason: "Employee forgot to submit",
    allow_negative_inventory: false, inventory_override_reason: "",
};

const EMPTY_EMPLOYEE = {
    personal_details: emptyPersonalDetails(),
    full_name: "", contact_number: "", email: "", address: "",
    primary_position_id: "", additional_position_ids: [],
    date_hired: today(), employment_type: "Regular", assigned_area: "", skills: "",
    employment_status: "Active", emergency_contact_name: "",
    emergency_contact_relationship: "", emergency_contact_number: "", notes: "",
    crop_assignment_ids: [], livestock_assignment_ids: [],
    create_login_account: true, login_username: "", login_password: "",
    login_password_confirm: "", has_login_account: false, login_status: null,
    schedule_needs_setup: false, weekly_schedule: makeWeeklySchedule(today()),
};

const CROP_RESOURCE_CATEGORIES = new Set([
    "Fertilizer", "Fertilizers", "Pesticide", "Pesticides",
    "Herbicide", "Herbicides", "Fungicide", "Fungicides", "Farm Supplies",
]);
const LIVESTOCK_RESOURCE_CATEGORIES = new Set([
    "Livestock Feed", "Animal Feed", "Feed", "Feeds", "Medicine", "Medicines",
    "Animal Medicine", "Livestock Medicine", "Vaccine", "Vaccines", "Vitamin",
    "Vitamins", "Supplement", "Supplements", "Disinfectant", "Disinfectants",
    "Cleaning Supplies", "Treatment Supply", "Treatment Supplies",
]);

const normalizeResourceText = (value) => String(value || "").trim().toLowerCase();

const resourceFitsTask = (item, module, taskText) => {
    const category = normalizeResourceText(item?.category);
    const name = normalizeResourceText(item?.name);
    const work = normalizeResourceText(taskText);

    if (module === "Crop") {
        if (category.includes("seed")) return false;
        if (work.includes("fertiliz")) return category.includes("fertiliz");
        if (work.includes("herbicide") || work.includes("weed control")) return category.includes("herbicide");
        if (work.includes("pesticide") || work.includes("pest control") || work.includes("insecticide")) {
            return category.includes("pesticide") || category.includes("insecticide");
        }
        if (work.includes("fungicide") || work.includes("fungal")) return category.includes("fungicide");
        return CROP_RESOURCE_CATEGORIES.has(item?.category);
    }

    if (module === "Livestock") {
        if (["seed", "seeds", "fertilizer", "fertilizers", "pesticide", "pesticides", "herbicide", "herbicides", "fungicide", "fungicides"].includes(category)) return false;
        if (work.includes("feed")) return ["livestock feed", "animal feed", "feed", "feeds"].includes(category);
        if (work.includes("vaccin") || work.includes("booster")) return ["vaccine", "vaccines"].includes(category) || name.includes("vaccine");
        if (work.includes("deworm") || work.includes("medicat") || work.includes("medicine") || work.includes("treatment")) {
            return ["medicine", "medicines", "animal medicine", "livestock medicine", "treatment supply", "treatment supplies"].includes(category);
        }
        if (work.includes("vitamin") || work.includes("supplement")) return ["vitamin", "vitamins", "supplement", "supplements"].includes(category);
        if (work.includes("clean") || work.includes("sanit") || work.includes("disinfect")) {
            return ["disinfectant", "disinfectants", "cleaning supplies"].includes(category);
        }
        return LIVESTOCK_RESOURCE_CATEGORIES.has(item?.category);
    }
    return false;
};


const suggestEmployeeUsername = (fullName) => String(fullName || "")
    .trim()
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, ".")
    .replace(/^\.+|\.+$/g, "")
    .slice(0, 50);

const employeePositionLabel = (employee) => {
    const positions = employee?.positions || [];
    if (!positions.length) return employee?.position || "Employee";
    const primary = positions.find((item) => item.is_primary) || positions[0];
    const extra = Math.max(positions.length - 1, 0);
    return extra ? `${primary.name} +${extra} more` : primary.name;
};

const TASK_DOMAIN_RULES = [
    {
        key: "crop",
        label: "Crop & Field Care",
        taskTerms: ["crop", "field", "plant", "seed", "seedling", "harvest", "fertiliz", "weed", "irrigat", "soil", "nursery", "eggplant", "calamansi", "tomato", "kamatis", "corn", "okra", "peanut", "sweet potato", "pineapple", "cabbage", "pechay", "ampalaya", "squash", "radish", "turmeric", "ginger"],
        positionTerms: ["crop", "farmer", "field", "agron", "horticultur", "plant", "harvest", "irrigation", "soil", "nursery"],
        suggestedRoles: ["Crop Farmer", "Crop Caretaker", "Field Worker", "General Farmer"],
    },
    {
        key: "livestock",
        label: "Livestock Care",
        taskTerms: ["livestock", "animal", "pen", "feeding", "feed", "vaccin", "booster", "health check", "weight check", "breeding", "goat", "sheep", "pig", "swine", "hog", "cattle", "carabao", "chicken", "poultry", "duck", "itik"],
        positionTerms: ["livestock", "animal", "caretaker", "herd", "feeding", "feed", "nutrition", "veterinary", "health"],
        suggestedRoles: ["Livestock Caretaker", "Animal Caretaker", "Feeding Assistant", "Animal Health Assistant"],
    },
    {
        key: "inventory",
        label: "Inventory & Supplies",
        taskTerms: ["inventory", "stock", "warehouse", "store room", "storeroom", "supply", "procurement", "reorder"],
        positionTerms: ["inventory", "storekeeper", "warehouse", "procurement", "stock", "supply"],
        suggestedRoles: ["Inventory Storekeeper", "Warehouse Assistant", "Procurement Assistant"],
    },
    {
        key: "equipment",
        label: "Equipment & Maintenance",
        taskTerms: ["equipment", "machine", "tractor", "repair", "maintenance", "mechanic", "pump", "motor"],
        positionTerms: ["equipment", "operator", "mechanic", "maintenance", "tractor", "technician"],
        suggestedRoles: ["Equipment Operator", "Maintenance Worker", "Farm Mechanic"],
    },
    {
        key: "logistics",
        label: "Logistics & Delivery",
        taskTerms: ["delivery", "deliver", "transport", "driver", "logistics", "dispatch", "sales"],
        positionTerms: ["delivery", "driver", "logistics", "transport", "sales", "dispatch"],
        suggestedRoles: ["Farm Driver", "Delivery Worker", "Logistics Assistant", "Sales Assistant"],
    },
    {
        key: "sanitation",
        label: "Sanitation & Biosecurity",
        taskTerms: ["clean", "cleaning", "sanitize", "sanitation", "disinfect", "biosecurity", "waste"],
        positionTerms: ["sanitation", "biosecurity", "clean", "waste", "farm worker", "caretaker"],
        suggestedRoles: ["Sanitation Worker", "Biosecurity Assistant", "General Farm Worker"],
    },
];

const TASK_ACTIVITY_RULES = [
    {
        key: "crop-growth",
        label: "Crop Growth Monitoring",
        taskTerms: ["growth check", "crop check", "crop monitoring", "plant monitoring", "growth monitoring"],
        domain: "crop",
        positionTerms: ["crop caretaker", "crop farmer", "crop production", "agron", "field"],
        suggestedRoles: ["Crop Caretaker", "Crop Farmer", "Crop Production Worker"],
    },
    {
        key: "harvest",
        label: "Harvest Work",
        taskTerms: ["harvest", "picking", "collect produce"],
        domain: "crop",
        positionTerms: ["harvest", "crop farmer", "crop caretaker", "field worker", "farmer"],
        suggestedRoles: ["Harvest Worker", "Crop Farmer", "Crop Caretaker"],
    },
    {
        key: "irrigation",
        label: "Irrigation Work",
        taskTerms: ["water field", "watering", "irrigat", "water crop"],
        domain: "crop",
        positionTerms: ["irrigation", "crop farmer", "crop caretaker", "field worker"],
        suggestedRoles: ["Irrigation Worker", "Crop Farmer", "Crop Caretaker"],
    },
    {
        key: "feeding",
        label: "Animal Feeding",
        taskTerms: ["feeding", "feed ", "ration"],
        domain: "livestock",
        positionTerms: ["feeding", "feed", "nutrition", "livestock caretaker", "animal caretaker"],
        suggestedRoles: ["Feeding Assistant", "Livestock Caretaker", "Animal Caretaker"],
    },
    {
        key: "animal-health",
        label: "Animal Health Care",
        taskTerms: ["vaccin", "booster", "health check", "treatment", "medication", "deworm", "veterinary"],
        domain: "livestock",
        positionTerms: ["animal health", "veterinary", "vaccination", "livestock caretaker", "animal caretaker"],
        suggestedRoles: ["Animal Health Assistant", "Veterinary Assistant", "Livestock Caretaker"],
    },
    {
        key: "breeding",
        label: "Breeding & Reproduction",
        taskTerms: ["breeding", "mating", "reproduction", "pregnancy", "farrowing", "calving", "kidding", "hatching"],
        domain: "livestock",
        positionTerms: ["breeding", "reproduction", "animal health", "livestock caretaker"],
        suggestedRoles: ["Breeding / Reproduction Assistant", "Animal Health Assistant", "Livestock Caretaker"],
    },
    {
        key: "goat-sheep",
        label: "Goat / Sheep Care",
        taskTerms: ["goat", "sheep", "kid", "doe", "buck"],
        domain: "livestock",
        positionTerms: ["goat", "sheep", "livestock caretaker", "animal caretaker"],
        suggestedRoles: ["Goat Caretaker", "Sheep Caretaker", "Livestock Caretaker"],
    },
    {
        key: "swine",
        label: "Swine Care",
        taskTerms: ["pig", "swine", "hog", "piglet", "sow", "boar"],
        domain: "livestock",
        positionTerms: ["swine", "pig", "hog", "livestock caretaker", "animal caretaker"],
        suggestedRoles: ["Swine Caretaker", "Livestock Caretaker", "Animal Caretaker"],
    },
    {
        key: "poultry",
        label: "Poultry Care",
        taskTerms: ["chicken", "poultry", "broiler", "layer", "chick"],
        domain: "livestock",
        positionTerms: ["poultry", "chicken", "livestock caretaker", "animal caretaker"],
        suggestedRoles: ["Poultry Caretaker", "Livestock Caretaker", "Animal Caretaker"],
    },
    {
        key: "duck",
        label: "Duck Care",
        taskTerms: ["duck", "itik"],
        domain: "livestock",
        positionTerms: ["duck", "itik", "poultry", "livestock caretaker", "animal caretaker"],
        suggestedRoles: ["Duck Caretaker", "Poultry Caretaker", "Livestock Caretaker"],
    },
    {
        key: "cattle",
        label: "Cattle / Carabao Care",
        taskTerms: ["cattle", "cow", "calf", "bull", "carabao"],
        domain: "livestock",
        positionTerms: ["cattle", "carabao", "livestock caretaker", "animal caretaker"],
        suggestedRoles: ["Cattle Caretaker", "Carabao Caretaker", "Livestock Caretaker"],
    },
];

const normalizeRecommendationText = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const includesAnyTerm = (text, terms) => terms.some((term) => text.includes(normalizeRecommendationText(term)));

const getTaskRecommendationProfile = (task) => {
    if (!task) return { domain: null, activities: [], suggestedRoles: ["General Farmer", "General Farm Worker"] };
    const taskText = normalizeRecommendationText([
        task.name,
        task.category,
        task.related_to,
        task.location,
        task.description,
        task.instructions,
        task.source_module,
        task.source_type,
    ].filter(Boolean).join(" "));

    const domain = TASK_DOMAIN_RULES.find((rule) => includesAnyTerm(taskText, rule.taskTerms)) || null;
    const activities = TASK_ACTIVITY_RULES.filter((rule) => {
        if (rule.domain && domain && rule.domain !== domain.key) return false;
        return includesAnyTerm(taskText, rule.taskTerms);
    });
    const suggestedRoles = [...new Set([
        ...activities.flatMap((rule) => rule.suggestedRoles || []),
        ...(domain?.suggestedRoles || []),
        "General Farmer",
        "General Farm Worker",
    ])].slice(0, 6);

    return { taskText, domain, activities, suggestedRoles };
};

const scoreEmployeeForTask = (employee, profile) => {
    const employeePositions = employee?.positions || [];
    let score = 0;
    const matchedPositions = [];
    const matchedReasons = new Set();

    employeePositions.forEach((position) => {
        const positionText = normalizeRecommendationText(`${position.name} ${position.category || ""}`);
        let positionScore = 0;

        if (profile.domain && includesAnyTerm(positionText, profile.domain.positionTerms)) {
            positionScore += position.is_primary ? 18 : 15;
            matchedReasons.add(profile.domain.label);
        }

        profile.activities.forEach((activity) => {
            if (includesAnyTerm(positionText, activity.positionTerms)) {
                positionScore += position.is_primary ? 24 : 20;
                matchedReasons.add(activity.label);
            }
        });

        if (includesAnyTerm(positionText, ["general farmer", "general farm worker", "farm worker"])) {
            positionScore += position.is_primary ? 5 : 4;
        }

        if (positionScore > 0) {
            matchedPositions.push({ ...position, match_score: positionScore });
            score += positionScore;
        }
    });

    if (employee.assigned_area && profile.taskText) {
        const area = normalizeRecommendationText(employee.assigned_area);
        const related = normalizeRecommendationText(profile.taskText);
        const usefulAreaWords = area.split(" ").filter((word) => word.length >= 4);
        if (usefulAreaWords.some((word) => related.includes(word))) score += 3;
    }

    const hasPrimaryMatch = matchedPositions.some((position) => position.is_primary);
    const hasSecondaryMatch = matchedPositions.some((position) => !position.is_primary);
    return {
        employee,
        score,
        matchedPositions: matchedPositions.sort((a, b) => b.match_score - a.match_score),
        matchedReasons: [...matchedReasons],
        hasPrimaryMatch,
        hasSecondaryMatch,
    };
};

export {
    today,
    addDaysToDateKey,
    EMPTY_TASK,
    EMPTY_ASSISTED_SUBMISSION,
    EMPTY_EMPLOYEE,
    resourceFitsTask,
    suggestEmployeeUsername,
    employeePositionLabel,
    normalizeRecommendationText,
    getTaskRecommendationProfile,
    scoreEmployeeForTask,
};
