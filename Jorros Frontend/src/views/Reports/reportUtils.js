// Shared formatting helpers for the Reports page
export function formatMonthLabel(value) {
    if (!value) {
        return "";
    }

    const [
        year,
        month,
    ] = String(value)
        .split("-")
        .map(Number);

    if (
        !year ||
        !month
    ) {
        return String(value);
    }

    return new Date(
        year,
        month - 1,
        1
    ).toLocaleDateString(
        "en-US",
        {
            month: "short",
            year: "2-digit",
        }
    );
}

export function formatMetricLabel(value) {
    return String(value || "")
        .replaceAll(
            "_",
            " "
        )
        .replace(
            /([A-Z])/g,
            " $1"
        )
        .replace(
            /\s+/g,
            " "
        )
        .trim()
        .replace(/^./, (character) =>
            character.toUpperCase()
        );
}

export function formatMetricValue(value) {
    if (
        typeof value ===
        "number"
    ) {
        return Number.isInteger(
            value
        )
            ? String(value)
            : value.toLocaleString(
                  "en-US",
                  {
                      maximumFractionDigits:
                          2,
                  }
              );
    }

    return String(
        value ?? "0"
    );
}

export function getTodayDate() {
    const date = new Date();

    const year =
        date.getFullYear();

    const month = String(
        date.getMonth() + 1
    ).padStart(2, "0");

    const day = String(
        date.getDate()
    ).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

export function formatDate(value) {
    if (!value) {
        return "Not specified";
    }

    const [
        year,
        month,
        day,
    ] = value
        .split("-")
        .map(Number);

    return new Date(
        year,
        month - 1,
        day
    ).toLocaleDateString(
        "en-US",
        {
            month: "short",
            day: "numeric",
            year: "numeric",
        }
    );
}

export function formatDateTime(value) {
    if (!value) {
        return "Not scheduled";
    }

    const date =
        new Date(
            value
        );

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return String(
            value
        );
    }

    return date.toLocaleString(
        "en-US",
        {
            month:
                "short",
            day:
                "numeric",
            year:
                "numeric",
            hour:
                "numeric",
            minute:
                "2-digit",
        }
    );
}


export function getClassName(
    value = ""
) {
    return String(value)
        .toLowerCase()
        .replaceAll("&", "and")
        .replaceAll(" ", "-")
        .replaceAll("/", "-");
}

export function getCategoryIcon(
    category
) {
    const icons = {
        Workforce: "badge",
        Tasks: "task_alt",
        "Care Compliance": "fact_check",
        Audit: "history",
        Farm: "analytics",
        Crop: "grass",
        Livestock: "pets",
        "Production & Sales": "point_of_sale",
        "Trend & Seasonal": "monitoring",
        Inventory:
            "inventory_2",
    };

    return (
        icons[category] ||
        "description"
    );
}
