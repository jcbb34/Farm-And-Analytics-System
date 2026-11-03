export const PHILIPPINE_REGIONS = [
    "Bicol Region",
    "Ilocos Region",
    "Cagayan Valley",
    "Central Luzon",
    "CALABARZON",
    "MIMAROPA",
    "Western Visayas",
    "Central Visayas",
    "Eastern Visayas",
    "Zamboanga Peninsula",
    "Northern Mindanao",
    "Davao Region",
    "SOCCSKSARGEN",
    "Caraga",
    "BARMM",
    "Cordillera Administrative Region",
    "National Capital Region",
];

export const MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];

export function getPhilippineSeason(monthNumber) {
    const month = Number(monthNumber);

    if ([12, 1, 2].includes(month)) {
        return {
            key: "cool-dry",
            name: "Cool Dry Season",
            description:
                "Generally cooler and drier conditions in the national seasonal baseline.",
        };
    }

    if ([3, 4, 5].includes(month)) {
        return {
            key: "hot-dry",
            name: "Hot Dry Season",
            description:
                "Generally hotter and drier conditions in the national seasonal baseline.",
        };
    }

    return {
        key: "rainy",
        name: "Rainy Season",
        description:
            "Generally wetter conditions in the national seasonal baseline.",
    };
}

// Bicol crops highlighted in DA Region V programs and production profiles.
const BICOL_PRIORITY_IDS = new Set([
    "ampalaya",
    "eggplant",
    "squash",
    "string-beans",
    "pineapple",
    "sweet-potato",
    "gabi",
    "tomato",
    "chili-pepper",
]);

const BICOL_PRODUCED_IDS = new Set([
    "corn",
    "peanut",
    "cassava",
    "okra",
    "mungbean",
    "pineapple",
    "sweet-potato",
    "gabi",
    "eggplant",
    "squash",
]);

/*
    Rule-based crop guide used by Farm Intelligence.
    Ranges are broad working ranges for decision support. They are not a
    substitute for field soil tests, variety recommendations, or LGU/DA advice.
*/
export const CROP_GUIDE = [
    {
        id: "rice",
        name: "Rice",
        aliases: ["palay"],
        icon: "agriculture",
        seasons: ["rainy"],
        secondarySeasons: ["cool-dry"],
        rainfall: ["Normal", "High"],
        irrigation: ["Full Irrigation", "Rainfed"],
        drainage: ["Moderate", "Good"],
        temperature: [22, 34],
        waterNeed: "High",
        cycleDays: "100–130 days",
        notes:
            "Strong candidate when dependable water is available. Drainage and flood risk still need to be checked.",
    },
    {
        id: "corn",
        name: "Corn",
        aliases: ["mais"],
        icon: "grass",
        seasons: ["rainy", "cool-dry"],
        secondarySeasons: ["hot-dry"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation", "Rainfed"],
        drainage: ["Good", "Moderate"],
        temperature: [21, 35],
        waterNeed: "Medium",
        cycleDays: "90–120 days",
        notes:
            "Adaptable across several planting windows, but waterlogging and severe moisture stress can reduce performance.",
    },
    {
        id: "tomato",
        name: "Tomato",
        aliases: ["kamatis", "camatis"],
        icon: "nutrition",
        seasons: ["cool-dry"],
        secondarySeasons: ["hot-dry"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation"],
        drainage: ["Good"],
        temperature: [18, 32],
        waterNeed: "Medium",
        cycleDays: "80–110 days",
        notes:
            "Usually easier to manage under drier conditions with good drainage and reliable irrigation.",
    },
    {
        id: "eggplant",
        name: "Eggplant",
        aliases: ["talong"],
        icon: "nutrition",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [22, 35],
        waterNeed: "Medium",
        cycleDays: "100–150 days",
        notes:
            "Warm-season vegetable that can perform well when prolonged waterlogging is avoided.",
    },
    {
        id: "mungbean",
        name: "Mungbean",
        aliases: ["mongo", "munggo"],
        icon: "eco",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: [],
        rainfall: ["Low", "Normal"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good"],
        temperature: [24, 35],
        waterNeed: "Low",
        cycleDays: "60–75 days",
        notes:
            "Short-duration legume that fits dry-season rotations and needs good drainage.",
    },
    {
        id: "peanut",
        name: "Peanut",
        aliases: ["mani"],
        icon: "eco",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: [],
        rainfall: ["Low", "Normal"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good"],
        temperature: [22, 34],
        waterNeed: "Low",
        cycleDays: "100–130 days",
        notes:
            "Best suited to well-drained soil; prolonged saturation is a major risk.",
    },
    {
        id: "sweet-potato",
        name: "Sweet Potato",
        aliases: ["kamote", "camote"],
        icon: "nutrition",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [21, 35],
        waterNeed: "Low",
        cycleDays: "90–150 days",
        notes:
            "Relatively tolerant of dry periods once established, but storage roots need well-drained soil.",
    },
    {
        id: "squash",
        name: "Squash",
        aliases: ["kalabasa", "calabasa"],
        icon: "nutrition",
        seasons: ["hot-dry", "cool-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation", "Rainfed"],
        drainage: ["Good", "Moderate"],
        temperature: [22, 35],
        waterNeed: "Medium",
        cycleDays: "90–120 days",
        notes:
            "Warm-season vine crop that benefits from steady moisture without standing water.",
    },
    {
        id: "pechay",
        name: "Pechay",
        aliases: ["petchay", "bok choy"],
        icon: "nutrition",
        seasons: ["cool-dry"],
        secondarySeasons: ["hot-dry"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [18, 30],
        waterNeed: "Medium",
        cycleDays: "30–45 days",
        notes:
            "Fast-growing leafy vegetable. Heat and prolonged heavy rain can reduce quality.",
    },
    {
        id: "okra",
        name: "Okra",
        aliases: [],
        icon: "nutrition",
        seasons: ["hot-dry", "rainy"],
        secondarySeasons: ["cool-dry"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [24, 36],
        waterNeed: "Low",
        cycleDays: "50–70 days",
        notes:
            "Heat tolerant and adaptable, provided the site drains properly.",
    },
    {
        id: "gabi",
        name: "Gabi / Taro",
        aliases: ["gabi", "taro"],
        icon: "nutrition",
        seasons: ["rainy"],
        secondarySeasons: ["cool-dry"],
        rainfall: ["Normal", "High"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Moderate", "Poor"],
        temperature: [21, 34],
        waterNeed: "High",
        cycleDays: "180–240 days",
        notes:
            "Moisture-loving root crop; suitability depends on variety, drainage, and production system.",
    },
    {
        id: "pineapple",
        name: "Pineapple",
        aliases: ["pinya"],
        icon: "nutrition",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good"],
        temperature: [21, 34],
        waterNeed: "Low",
        cycleDays: "12–18 months",
        notes:
            "Perennial fruit crop that needs strong drainage; prolonged saturated soil is risky.",
    },
    {
        id: "ampalaya",
        name: "Ampalaya",
        aliases: ["bitter melon", "bitter gourd"],
        icon: "nutrition",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation", "Rainfed"],
        drainage: ["Good", "Moderate"],
        temperature: [24, 33],
        waterNeed: "Medium",
        cycleDays: "70–100 days",
        notes:
            "Warm-season vine crop that performs best with good drainage and steady moisture.",
    },
    {
        id: "string-beans",
        name: "String Beans",
        aliases: ["sitaw", "yardlong bean", "string bean"],
        icon: "eco",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [22, 35],
        waterNeed: "Medium",
        cycleDays: "55–75 days",
        notes:
            "Fast-producing legume that needs trellising and good drainage during wet periods.",
    },
    {
        id: "chili-pepper",
        name: "Siling Labuyo / Chili",
        aliases: ["labuyo", "siling labuyo", "siling mahaba", "chili", "chili pepper"],
        icon: "nutrition",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation", "Rainfed"],
        drainage: ["Good", "Moderate"],
        temperature: [21, 34],
        waterNeed: "Medium",
        cycleDays: "90–150 days",
        notes:
            "Can produce for an extended period when drainage, pest pressure, and moisture are managed well.",
    },
    {
        id: "cassava",
        name: "Cassava",
        aliases: ["kamoteng kahoy", "balanghoy"],
        icon: "nutrition",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [22, 35],
        waterNeed: "Low",
        cycleDays: "8–12 months",
        notes:
            "Drought-tolerant root crop once established, but root development still benefits from loose, well-drained soil.",
    },
    {
        id: "bottle-gourd",
        name: "Upo / Bottle Gourd",
        aliases: ["upo", "opo", "bottle gourd"],
        icon: "nutrition",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation", "Rainfed"],
        drainage: ["Good", "Moderate"],
        temperature: [22, 34],
        waterNeed: "Medium",
        cycleDays: "60–90 days",
        notes:
            "Vine crop suited to warm conditions with trellising, steady moisture, and good drainage.",
    },
    {
        id: "patola",
        name: "Patola / Sponge Gourd",
        aliases: ["patola", "sponge gourd"],
        icon: "nutrition",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation", "Rainfed"],
        drainage: ["Good", "Moderate"],
        temperature: [22, 34],
        waterNeed: "Medium",
        cycleDays: "70–100 days",
        notes:
            "Warm vine crop that benefits from trellising and drainage during prolonged rain.",
    },
    {
        id: "chayote",
        name: "Sayote / Chayote",
        aliases: ["sayote", "chayote"],
        icon: "nutrition",
        seasons: ["cool-dry", "rainy"],
        secondarySeasons: ["hot-dry"],
        rainfall: ["Normal", "High"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [18, 30],
        waterNeed: "Medium",
        cycleDays: "4–6 months to first harvest",
        notes:
            "Perennial vine that generally prefers cooler conditions, steady moisture, and well-drained soil.",
    },
    {
        id: "cabbage",
        name: "Cabbage",
        aliases: ["cabage", "repolyo"],
        icon: "nutrition",
        seasons: ["cool-dry"],
        secondarySeasons: [],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation"],
        drainage: ["Good"],
        temperature: [15, 27],
        waterNeed: "Medium",
        cycleDays: "75–120 days",
        notes:
            "Cooler conditions are preferred; lowland heat can reduce head quality and increase stress.",
    },
    {
        id: "radish",
        name: "Radish",
        aliases: ["labanos"],
        icon: "nutrition",
        seasons: ["cool-dry"],
        secondarySeasons: ["hot-dry"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation"],
        drainage: ["Good"],
        temperature: [16, 30],
        waterNeed: "Medium",
        cycleDays: "30–60 days",
        notes:
            "Fast root crop that benefits from loose soil, even moisture, and cooler temperatures.",
    },
    {
        id: "ginger",
        name: "Ginger",
        aliases: ["luya"],
        icon: "nutrition",
        seasons: ["rainy"],
        secondarySeasons: ["cool-dry"],
        rainfall: ["Normal", "High"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [22, 32],
        waterNeed: "Medium",
        cycleDays: "8–10 months",
        notes:
            "Needs consistent moisture but rhizomes are sensitive to prolonged waterlogging.",
    },
    {
        id: "turmeric",
        name: "Turmeric",
        aliases: ["luyang dilaw"],
        icon: "nutrition",
        seasons: ["rainy"],
        secondarySeasons: ["cool-dry"],
        rainfall: ["Normal", "High"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [22, 32],
        waterNeed: "Medium",
        cycleDays: "8–10 months",
        notes:
            "Rhizome crop that needs moisture during growth and good drainage to limit rot risk.",
    },
    {
        id: "onion",
        name: "Onion",
        aliases: ["sibuyas", "sibuya"],
        icon: "nutrition",
        seasons: ["cool-dry"],
        secondarySeasons: ["hot-dry"],
        rainfall: ["Low"],
        irrigation: ["Limited Irrigation", "Full Irrigation"],
        drainage: ["Good"],
        temperature: [18, 30],
        waterNeed: "Medium",
        cycleDays: "90–130 days",
        notes:
            "Bulb development is generally favored by dry weather, reliable irrigation, and excellent drainage.",
    },
    {
        id: "garlic",
        name: "Garlic",
        aliases: ["bawang"],
        icon: "nutrition",
        seasons: ["cool-dry"],
        secondarySeasons: [],
        rainfall: ["Low"],
        irrigation: ["Limited Irrigation", "Full Irrigation"],
        drainage: ["Good"],
        temperature: [18, 30],
        waterNeed: "Low",
        cycleDays: "100–150 days",
        notes:
            "Prefers a dry production window and well-drained soil; prolonged rain increases bulb disease risk.",
    },
    {
        id: "singkamas",
        name: "Singkamas / Jicama",
        aliases: ["singkamas", "jicama"],
        icon: "nutrition",
        seasons: ["cool-dry", "hot-dry"],
        secondarySeasons: ["rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good"],
        temperature: [22, 34],
        waterNeed: "Medium",
        cycleDays: "4–6 months",
        notes:
            "Root crop that needs loose, well-drained soil and moderate moisture for good root development.",
    },
    {
        id: "calamansi",
        name: "Calamansi",
        aliases: ["calamondin", "kalamansi"],
        icon: "nutrition",
        seasons: ["cool-dry", "hot-dry", "rainy"],
        secondarySeasons: [],
        rainfall: ["Low", "Normal", "High"],
        irrigation: ["Rainfed", "Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [22, 35],
        waterNeed: "Medium",
        cycleDays: "Perennial",
        notes:
            "Perennial citrus that can grow year-round when drainage, nutrition, and water supply are managed.",
    },
    {
        id: "spring-onion",
        name: "Spring Onion",
        aliases: ["green onion", "scallion", "dahon ng sibuyas"],
        icon: "nutrition",
        seasons: ["cool-dry"],
        secondarySeasons: ["hot-dry", "rainy"],
        rainfall: ["Low", "Normal"],
        irrigation: ["Limited Irrigation", "Full Irrigation"],
        drainage: ["Good", "Moderate"],
        temperature: [18, 30],
        waterNeed: "Medium",
        cycleDays: "45–70 days",
        notes:
            "Short-duration leafy allium that needs even moisture and good drainage.",
    },
];

function scoreTemperature(crop, temperature) {
    const temp = Number(temperature);

    if (!Number.isFinite(temp)) {
        return { score: 0, reason: "" };
    }

    if (temp >= crop.temperature[0] && temp <= crop.temperature[1]) {
        return {
            score: 12,
            reason: `Temperature is within the ${crop.temperature[0]}–${crop.temperature[1]}°C working range used by this prototype.`,
        };
    }

    const difference = Math.min(
        Math.abs(temp - crop.temperature[0]),
        Math.abs(temp - crop.temperature[1])
    );

    if (difference <= 3) {
        return {
            score: 2,
            reason:
                "Temperature is just outside the preferred range, so suitability is reduced only slightly.",
        };
    }

    return {
        score: -8,
        reason:
            "Temperature is well outside the preferred working range for this crop.",
    };
}

function getRegionalScore(crop, region) {
    if (region !== "Bicol Region") {
        return {
            score: 0,
            reason:
                "No Joross-specific regional bonus is configured for this region; seasonal and live farm conditions carry the score.",
        };
    }

    if (BICOL_PRIORITY_IDS.has(crop.id)) {
        return {
            score: 8,
            reason:
                "Bicol regional fit: this crop is included among DA Region V priority high-value commodities.",
        };
    }

    if (BICOL_PRODUCED_IDS.has(crop.id)) {
        return {
            score: 5,
            reason:
                "Bicol regional fit: this crop appears in documented regional production profiles.",
        };
    }

    return {
        score: 0,
        reason:
            "Bicol is selected, but no extra regional commodity bonus is applied to this crop.",
    };
}

export function recommendCrops({
    month,
    rainfall,
    irrigation,
    drainage,
    temperature,
    region,
}) {
    const season = getPhilippineSeason(month);

    return CROP_GUIDE.map((crop) => {
        let score = 25;
        const reasons = [];
        const scoreBreakdown = {
            base: 25,
            season: 0,
            rainfall: 0,
            irrigation: 0,
            drainage: 0,
            temperature: 0,
            region: 0,
        };

        if (crop.seasons.includes(season.key)) {
            scoreBreakdown.season = 20;
            reasons.push(
                `Strong seasonal fit for the ${season.name.toLowerCase()}.`
            );
        } else if (crop.secondarySeasons.includes(season.key)) {
            scoreBreakdown.season = 10;
            reasons.push(
                "This is a secondary planting window and needs closer field management."
            );
        } else {
            scoreBreakdown.season = -12;
            reasons.push(
                "This is not the strongest seasonal window in the prototype guide."
            );
        }
        score += scoreBreakdown.season;

        if (crop.rainfall.includes(rainfall)) {
            scoreBreakdown.rainfall = 12;
            reasons.push(
                `${rainfall.toLowerCase()} expected rainfall matches its general moisture preference.`
            );
        } else if (rainfall === "High" && crop.waterNeed === "Low") {
            scoreBreakdown.rainfall = -14;
            reasons.push(
                "High rainfall may increase waterlogging or disease pressure."
            );
        } else if (rainfall === "Low" && crop.waterNeed === "High") {
            scoreBreakdown.rainfall = -16;
            reasons.push(
                "Low rainfall is risky for a crop with high water demand."
            );
        } else {
            scoreBreakdown.rainfall = -4;
            reasons.push(
                "Rainfall is usable but not an ideal match for this crop."
            );
        }
        score += scoreBreakdown.rainfall;

        if (crop.irrigation.includes(irrigation)) {
            scoreBreakdown.irrigation = 8;
        } else if (
            crop.waterNeed === "High" &&
            irrigation === "Rainfed" &&
            rainfall !== "High"
        ) {
            scoreBreakdown.irrigation = -14;
            reasons.push(
                "Water supply may be insufficient without dependable rainfall."
            );
        } else {
            scoreBreakdown.irrigation = -3;
        }
        score += scoreBreakdown.irrigation;

        if (crop.drainage.includes(drainage)) {
            scoreBreakdown.drainage = 8;
        } else if (
            rainfall === "High" &&
            drainage === "Poor" &&
            crop.id !== "gabi"
        ) {
            scoreBreakdown.drainage = -16;
            reasons.push(
                "Poor drainage plus high rainfall raises waterlogging risk."
            );
        } else {
            scoreBreakdown.drainage = -4;
        }
        score += scoreBreakdown.drainage;

        const temperatureScore = scoreTemperature(crop, temperature);
        scoreBreakdown.temperature = temperatureScore.score;
        score += temperatureScore.score;

        if (temperatureScore.reason) {
            reasons.push(temperatureScore.reason);
        }

        const regionalScore = getRegionalScore(crop, region);
        scoreBreakdown.region = regionalScore.score;
        score += regionalScore.score;
        reasons.push(regionalScore.reason);

        score = Math.max(0, Math.min(100, Math.round(score)));

        return {
            ...crop,
            score,
            scoreBreakdown,
            suitability:
                score >= 82
                    ? "Highly Suitable"
                    : score >= 68
                      ? "Suitable"
                      : score >= 52
                        ? "Conditional"
                        : "Not Preferred",
            reasons,
        };
    }).sort((a, b) => b.score - a.score);
}
