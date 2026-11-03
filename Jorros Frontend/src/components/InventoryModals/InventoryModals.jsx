"use client";

import FarmLocationInput from "../FarmLocationInput/FarmLocationInput.jsx";
import { notify } from "../../context/NotificationContext.jsx";

import {
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import {
    clearStableIdempotencyKey,
    stableIdempotencyKey,
} from "../../services/idempotencyKey.js";
import "./InventoryModals.css";

const inventoryCategories = [
    "Seeds",
    "Fertilizer",
    "Pesticide",
    "Herbicide",
    "Livestock Feed",
    "Animal Feed",
    "Medicine",
    "Animal Medicine",
    "Vaccine",
    "Vitamins",
    "Cleaning Supplies",
    "Farm Supplies",
    "Farm Tools",
    "Farm Equipment",
    "Farm Product",
    "Processed Product",
    "Other",
];

const inventoryUnits = [
    "kilograms",
    "grams",
    "liters",
    "milliliters",
    "doses",
    "bags",
    "packs",
    "bottles",
    "vials",
    "boxes",
    "pieces",
    "sets",
    "pairs",
];

const stockAdjustmentTypes = [
    "Restock",
    "Stock Usage",
    "Damaged",
    "Expired",
    "Lost",
    "Correction",
    "Returned",
    "Set Exact Quantity",
];

function getTodayDate() {
    const today = new Date();

    const year = today.getFullYear();

    const month = String(
        today.getMonth() + 1
    ).padStart(2, "0");

    const day = String(
        today.getDate()
    ).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

function formatDate(dateValue) {
    if (!dateValue) {
        return "Not specified";
    }

    const [year, month, day] =
        dateValue.split("-").map(Number);

    const date = new Date(
        year,
        month - 1,
        day
    );

    return date.toLocaleDateString(
        "en-US",
        {
            month: "long",
            day: "numeric",
            year: "numeric",
        }
    );
}

function formatCurrency(value) {
    return Number(
        value || 0
    ).toLocaleString("en-PH", {
        style: "currency",
        currency: "PHP",
        minimumFractionDigits: 2,
    });
}

function getStockStatus(item) {
    const quantity = Number(
        item.quantity || 0
    );

    const reorderLevel = Number(
        item.reorderLevel || 0
    );

    if (quantity <= 0) {
        return "Out of Stock";
    }

    if (quantity <= reorderLevel) {
        return "Low Stock";
    }

    return "In Stock";
}

function getStatusClass(value = "") {
    return value
        .toLowerCase()
        .replaceAll(" ", "-");
}

function createEmptyInventoryForm() {
    return {
        name: "",
        category: "Fertilizer",
        batchNumber: "",
        quantity: "",
        unit: "bags",
        reorderLevel: "",
        cost: "",
        price: "",
        isSaleable: false,
        supplier: "",
        dateAcquired: getTodayDate(),
        expirationDate: "",
        location: "",
        description: "",
        notes: "",
    };
}

function createInventoryFormFromItem(
    item
) {
    if (!item) {
        return createEmptyInventoryForm();
    }

    return {
        name: item.name || "",

        category:
            item.category ||
            "Fertilizer",

        batchNumber:
            item.batchNumber || "",

        quantity: String(
            item.quantity ?? ""
        ),

        unit:
            item.unit || "bags",

        reorderLevel: String(
            item.reorderLevel ?? ""
        ),

        cost: String(
            item.cost ?? ""
        ),

        price: String(
            item.price ?? ""
        ),

        isSaleable: Boolean(item.isSaleable),

        supplier:
            item.supplier || "",

        dateAcquired:
            item.dateAcquired ||
            getTodayDate(),

        expirationDate:
            item.expirationDate ||
            "",

        location:
            item.location || "",

        description:
            item.description || "",

        notes:
            item.notes || "",
    };
}

/* =========================================================
   ADD AND EDIT INVENTORY FORM
========================================================= */

export function InventoryFormModal({
    storageOptions = [],
    open,
    item,
    onClose,
    onSave,
}) {
    const inventorySubmittingRef = useRef(false);
    const inventoryCreateRequestRef = useRef(null);
    const [inventorySaving, setInventorySaving] = useState(false);
    const [form, setForm] =
        useState(
            createEmptyInventoryForm
        );

    const isEditing =
        Boolean(item);

    useEffect(() => {
        if (!open) {
            return;
        }

        inventorySubmittingRef.current = false;
        clearStableIdempotencyKey(inventoryCreateRequestRef);
        setInventorySaving(false);
        setForm(
            createInventoryFormFromItem(
                item
            )
        );

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open, item]);

    if (!open) {
        return null;
    }

    const handleChange = (event) => {
        const { name, value, type, checked } =
            event.target;

        setForm((currentForm) => ({
            ...currentForm,
            [name]: type === "checkbox" ? checked : value,
        }));
    };

    const closeForm = () => { if (!inventorySubmittingRef.current) onClose(); };

    const handleSubmit = async (event) => {
        event.preventDefault();
        if (inventorySubmittingRef.current) return;

        const requiredFields = [
            "name",
            "category",
            "unit",
            "reorderLevel",
            "cost",
            "price",
            "supplier",
            "dateAcquired",
            "location",
        ];

        if (!isEditing) {
            requiredFields.push("quantity");
        }

        const hasMissingField =
            requiredFields.some(
                (fieldName) =>
                    !String(
                        form[fieldName]
                    ).trim()
            );

        if (hasMissingField) {
            notify(
                "Please complete all required inventory fields."
            );

            return;
        }

        const quantity = Number(
            form.quantity
        );

        const reorderLevel =
            Number(
                form.reorderLevel
            );

        const cost = Number(
            form.cost
        );

        const price = Number(
            form.price
        );

        if (
            Number.isNaN(quantity) ||
            quantity < 0
        ) {
            notify(
                "Quantity must be zero or greater."
            );

            return;
        }

        if (
            Number.isNaN(
                reorderLevel
            ) ||
            reorderLevel < 0
        ) {
            notify(
                "Reorder level must be zero or greater."
            );

            return;
        }

        if (
            Number.isNaN(cost) ||
            cost < 0
        ) {
            notify(
                "Cost must contain a valid amount."
            );

            return;
        }

        if (
            Number.isNaN(price) ||
            price < 0
        ) {
            notify(
                "Price must contain a valid amount."
            );

            return;
        }

        if (
            form.expirationDate &&
            form.expirationDate <
                form.dateAcquired
        ) {
            notify(
                "Expiration date cannot be earlier than the date acquired."
            );

            return;
        }

        const payload = {
            name: form.name.trim(),

            category:
                form.category,

            batchNumber:
                form.batchNumber.trim(),

            ...(isEditing ? {} : { quantity }),

            unit: form.unit,

            reorderLevel,

            cost,

            price,

            isSaleable: form.isSaleable,

            supplier:
                form.supplier.trim(),

            dateAcquired:
                form.dateAcquired,

            expirationDate:
                form.expirationDate,

            location:
                form.location.trim(),

            description:
                form.description.trim() ||
                "No description provided.",

            notes:
                form.notes.trim() ||
                "No additional notes.",
        };
        const idempotencyKey = isEditing ? null : stableIdempotencyKey(inventoryCreateRequestRef, payload, "inventory-create");
        inventorySubmittingRef.current = true;
        setInventorySaving(true);
        try {
            const saved = await onSave(payload, { idempotencyKey });
            if (saved !== false) clearStableIdempotencyKey(inventoryCreateRequestRef);
        } catch (error) {
            notify(error?.message || "Unable to save inventory record. Your entries are kept; retry when ready.");
        } finally {
            inventorySubmittingRef.current = false;
            setInventorySaving(false);
        }
    };

    const previewStatus =
        getStockStatus({
            quantity:
                Number(
                    form.quantity
                ) || 0,

            reorderLevel:
                Number(
                    form.reorderLevel
                ) || 0,
        });

    const totalStockCost =
        (Number(form.quantity) ||
            0) *
        (Number(form.cost) || 0);

    const unitDifference =
        (Number(form.price) ||
            0) -
        (Number(form.cost) || 0);

    return (
        <div
            className="inventory-modal-overlay"
            onMouseDown={closeForm}
        >
            <div
                className="inventory-form-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="inventory-modal-header">
                    <div>
                        <h2>
                            {isEditing
                                ? "Edit Inventory"
                                : "Add Inventory"}
                        </h2>

                        <p>
                            {isEditing
                                ? `Update ${item.name} (${item.itemCode}) and save the changes.`
                                : "Create a new farm inventory record with stock, supplier, and acquisition information."}
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={closeForm}
                        disabled={inventorySaving}
                        aria-label="Close inventory form"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <form
                    className="inventory-modal-form"
                    aria-busy={inventorySaving}
                    onSubmit={
                        handleSubmit
                    }
                >
                    <fieldset className="inventory-form-fields" disabled={inventorySaving}>
                    <section className="inventory-form-section">
                        <div className="inventory-form-section-title">
                            <span className="material-symbols-outlined">
                                inventory_2
                            </span>

                            <div>
                                <h3>
                                    Item Information
                                </h3>

                                <p>
                                    Enter the item name,
                                    category, supplier,
                                    and storage location.
                                </p>
                            </div>
                        </div>

                        <div className="inventory-form-grid">
                            <div className="inventory-form-group">
                                <label htmlFor="inventoryItemName">
                                    Item Name
                                    <span>*</span>
                                </label>

                                <input
                                    id="inventoryItemName"
                                    name="name"
                                    type="text"
                                    placeholder="Example: Complete Fertilizer"
                                    value={
                                        form.name
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="inventory-form-group">
                                <label htmlFor="inventoryCategory">
                                    Category
                                    <span>*</span>
                                </label>

                                <select
                                    id="inventoryCategory"
                                    name="category"
                                    value={
                                        form.category
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                >
                                    {inventoryCategories.map(
                                        (
                                            category
                                        ) => (
                                            <option
                                                key={
                                                    category
                                                }
                                                value={
                                                    category
                                                }
                                            >
                                                {
                                                    category
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>

                            <div className="inventory-form-group">
                                <label htmlFor="inventorySupplier">
                                    Supplier
                                    <span>*</span>
                                </label>

                                <input
                                    id="inventorySupplier"
                                    name="supplier"
                                    type="text"
                                    placeholder="Example: Agri Supply Center"
                                    value={
                                        form.supplier
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="inventory-form-group">
                                <label htmlFor="inventoryBatchNumber">
                                    Batch / Lot Number
                                </label>

                                <input
                                    id="inventoryBatchNumber"
                                    name="batchNumber"
                                    type="text"
                                    placeholder="Example: LOT-2026-08-A"
                                    value={form.batchNumber}
                                    onChange={handleChange}
                                />
                            </div>

                            <div className="inventory-form-group">
                                <label htmlFor="inventoryLocation">
                                    Storage Location
                                    <span>*</span>
                                </label>

                                <FarmLocationInput id="inventoryLocation" name="location" label="Storage Location" knownOptions={storageOptions} context="inventory" active={open} value={form.location} onValueChange={(location) => setForm((old) => ({ ...old, location }))} required />
                            </div>
                        </div>

                        <div className="inventory-form-group">
                            <label htmlFor="inventoryDescription">
                                Item Description
                            </label>

                            <textarea
                                id="inventoryDescription"
                                name="description"
                                rows="3"
                                placeholder="Enter a short description of the inventory item..."
                                value={
                                    form.description
                                }
                                onChange={
                                    handleChange
                                }
                            />
                        </div>
                    </section>

                    <section className="inventory-form-section">
                        <div className="inventory-form-section-title">
                            <span className="material-symbols-outlined">
                                stacked_bar_chart
                            </span>

                            <div>
                                <h3>
                                    Stock Information
                                </h3>

                                <p>
                                    Add the opening quantity for new items. Existing stock is changed only through Stock Adjustment.
                                </p>
                            </div>
                        </div>

                        <div className="inventory-form-grid">
                            <div className="inventory-form-group">
                                <label htmlFor="inventoryQuantity">
                                    Current Quantity
                                    <span>*</span>
                                </label>

                                <input
                                    id="inventoryQuantity"
                                    name="quantity"
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    placeholder="0"
                                    value={form.quantity}
                                    onChange={handleChange}
                                    readOnly={isEditing}
                                    required={!isEditing}
                                />
                                {isEditing && (
                                    <small className="inventory-quantity-lock-note">
                                        Use Stock Adjustment to change quantity so a reason and history record are always saved.
                                    </small>
                                )}
                            </div>

                            <div className="inventory-form-group">
                                <label htmlFor="inventoryUnit">
                                    Unit
                                    <span>*</span>
                                </label>

                                <select
                                    id="inventoryUnit"
                                    name="unit"
                                    value={
                                        form.unit
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    disabled={isEditing}
                                    required
                                >
                                    {form.unit && !inventoryUnits.includes(form.unit) && <option value={form.unit}>{form.unit}</option>}
                                    {inventoryUnits.map(
                                        (unit) => (
                                            <option
                                                key={
                                                    unit
                                                }
                                                value={
                                                    unit
                                                }
                                            >
                                                {
                                                    unit
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                                {isEditing && (
                                    <small className="inventory-quantity-lock-note">
                                        Existing item units are locked to keep usage and transaction history consistent.
                                    </small>
                                )}
                            </div>

                            <div className="inventory-form-group">
                                <label htmlFor="inventoryReorderLevel">
                                    Reorder Level
                                    <span>*</span>
                                </label>

                                <input
                                    id="inventoryReorderLevel"
                                    name="reorderLevel"
                                    type="number"
                                    min="0"
                                    step="0.01"
                                    placeholder="0"
                                    value={
                                        form.reorderLevel
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="inventory-form-group">
                                <label>
                                    Current Status
                                </label>

                                <div
                                    className={`inventory-form-status-preview ${getStatusClass(
                                        previewStatus
                                    )}`}
                                >
                                    <span className="material-symbols-outlined">
                                        inventory
                                    </span>

                                    {
                                        previewStatus
                                    }
                                </div>
                            </div>
                        </div>
                    </section>

                    <section className="inventory-form-section">
                        <div className="inventory-form-section-title">
                            <span className="material-symbols-outlined">
                                payments
                            </span>

                            <div>
                                <h3>
                                    Cost and Pricing
                                </h3>

                                <p>
                                    Record the unit cost,
                                    price, and total stock
                                    value.
                                </p>
                            </div>
                        </div>

                        <div className="inventory-form-grid">
                            <div className="inventory-form-group">
                                <label htmlFor="inventoryCost">
                                    Unit Cost
                                    <span>*</span>
                                </label>

                                <div className="inventory-money-input">
                                    <span>₱</span>

                                    <input
                                        id="inventoryCost"
                                        name="cost"
                                        type="number"
                                        min="0"
                                        step="0.01"
                                        placeholder="0.00"
                                        value={
                                            form.cost
                                        }
                                        onChange={
                                            handleChange
                                        }
                                        required
                                    />
                                </div>
                            </div>

                            <div className="inventory-form-group">
                                <label htmlFor="inventoryPrice">
                                    Unit Price
                                    <span>*</span>
                                </label>

                                <div className="inventory-money-input">
                                    <span>₱</span>

                                    <input
                                        id="inventoryPrice"
                                        name="price"
                                        type="number"
                                        min="0"
                                        step="0.01"
                                        placeholder="0.00"
                                        value={
                                            form.price
                                        }
                                        onChange={
                                            handleChange
                                        }
                                        required
                                    />
                                </div>
                            </div>

                            <div className="inventory-form-group">
                                <label>
                                    Total Stock Cost
                                </label>

                                <div className="inventory-readonly-value">
                                    {formatCurrency(
                                        totalStockCost
                                    )}
                                </div>
                            </div>

                            <div className="inventory-form-group">
                                <label>
                                    Unit Difference
                                </label>

                                <div className="inventory-readonly-value">
                                    {formatCurrency(
                                        unitDifference
                                    )}
                                </div>
                            </div>

                            <div className="inventory-form-group full-width">
                                <label className="inventory-saleable-option" htmlFor="inventoryIsSaleable">
                                    <input
                                        id="inventoryIsSaleable"
                                        name="isSaleable"
                                        type="checkbox"
                                        checked={form.isSaleable}
                                        onChange={handleChange}
                                    />
                                    <span>
                                        <strong>Available for customer sales</strong>
                                        <small>Enable only for finished farm products or other goods that may be added to an invoice. Inputs such as feed, fertilizer, pesticide, and medicine should normally remain off.</small>
                                    </span>
                                </label>
                            </div>
                        </div>
                    </section>

                    <section className="inventory-form-section">
                        <div className="inventory-form-section-title">
                            <span className="material-symbols-outlined">
                                calendar_month
                            </span>

                            <div>
                                <h3>
                                    Acquisition Details
                                </h3>

                                <p>
                                    Record when the item
                                    arrived and when it
                                    expires.
                                </p>
                            </div>
                        </div>

                        <div className="inventory-form-grid">
                            <div className="inventory-form-group">
                                <label htmlFor="inventoryDateAcquired">
                                    Date Acquired
                                    <span>*</span>
                                </label>

                                <input
                                    id="inventoryDateAcquired"
                                    name="dateAcquired"
                                    type="date"
                                    value={
                                        form.dateAcquired
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="inventory-form-group">
                                <label htmlFor="inventoryExpirationDate">
                                    Expiration Date
                                </label>

                                <input
                                    id="inventoryExpirationDate"
                                    name="expirationDate"
                                    type="date"
                                    value={
                                        form.expirationDate
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>
                        </div>

                        <div className="inventory-form-group">
                            <label htmlFor="inventoryNotes">
                                Notes
                            </label>

                            <textarea
                                id="inventoryNotes"
                                name="notes"
                                rows="4"
                                placeholder="Enter storage instructions, handling details, or other notes..."
                                value={
                                    form.notes
                                }
                                onChange={
                                    handleChange
                                }
                            />
                        </div>
                    </section>

                    </fieldset>
                    <footer className="inventory-form-footer">
                        <button
                            type="button"
                            className="inventory-modal-cancel"
                            onClick={closeForm}
                            disabled={inventorySaving}
                        >
                            Cancel
                        </button>

                        <button
                            type="submit"
                            className="inventory-modal-save"
                            disabled={inventorySaving}
                        >
                            <span className="material-symbols-outlined">
                                save
                            </span>

                            {inventorySaving ? "Saving Inventory..." : isEditing
                                ? "Save Changes"
                                : "Save Inventory"}
                        </button>
                    </footer>
                </form>
            </div>
        </div>
    );
}

/* =========================================================
   INVENTORY DETAILS AND STOCK ADJUSTMENT
========================================================= */

export function InventoryDetailsModal({
    item,
    onClose,
    onAdjustStock,
}) {
    const [
        activeTab,
        setActiveTab,
    ] = useState("overview");

    const [
        adjustmentForm,
        setAdjustmentForm,
    ] = useState({
        type: "Restock",
        quantity: "",
        date: getTodayDate(),
        reason: "",
        reference: "",
        supplier: "",
    });

    const [adjustmentSaving, setAdjustmentSaving] = useState(false);
    const adjustmentSubmittingRef = useRef(false);
    const adjustmentRequestRef = useRef(null);

    useEffect(() => {
        if (!item) {
            return;
        }

        setActiveTab("overview");

        setAdjustmentForm({
            type: "Restock",
            quantity: "",
            date: getTodayDate(),
            reason: "",
            reference: "",
            supplier:
                item.supplier || "",
        });
        adjustmentSubmittingRef.current = false;
        setAdjustmentSaving(false);
        clearStableIdempotencyKey(adjustmentRequestRef);

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [item]);

    const projectedQuantity =
        useMemo(() => {
            if (!item) {
                return 0;
            }

            const currentQuantity =
                Number(
                    item.quantity
                ) || 0;

            const enteredQuantity =
                Number(
                    adjustmentForm.quantity
                );

            if (
                adjustmentForm.quantity ===
                    "" ||
                Number.isNaN(
                    enteredQuantity
                )
            ) {
                return currentQuantity;
            }

            if (
                ["Restock", "Returned"].includes(
                    adjustmentForm.type
                )
            ) {
                return (
                    currentQuantity +
                    enteredQuantity
                );
            }

            if (
                adjustmentForm.type ===
                "Set Exact Quantity"
            ) {
                return Math.max(
                    0,
                    enteredQuantity
                );
            }

            return Math.max(
                0,
                currentQuantity -
                    enteredQuantity
            );
        }, [item, adjustmentForm]);

    if (!item) {
        return null;
    }

    const stockStatus =
        getStockStatus(item);

    const stockHistory =
        item.stockHistory || [];

    const handleAdjustmentChange = (
        event
    ) => {
        const { name, value } =
            event.target;

        setAdjustmentForm(
            (currentForm) => ({
                ...currentForm,
                [name]: value,
            })
        );
    };

    const handleAdjustmentSubmit = async (
        event
    ) => {
        event.preventDefault();

        // Ref guard closes the tiny gap before React can render the disabled
        // button, so rapid double-clicks still produce only one request.
        if (adjustmentSubmittingRef.current) {
            return;
        }

        const quantity = Number(
            adjustmentForm.quantity
        );

        if (
            adjustmentForm.quantity ===
                "" ||
            Number.isNaN(quantity) ||
            quantity < 0
        ) {
            notify(
                "Please enter a valid stock quantity."
            );

            return;
        }

        if (
            adjustmentForm.type !==
                "Set Exact Quantity" &&
            quantity <= 0
        ) {
            notify(
                "Adjustment quantity must be greater than zero."
            );

            return;
        }

        const quantityRemovalTypes = [
            "Stock Usage",
            "Damaged",
            "Expired",
            "Lost",
            "Correction",
        ];

        if (
            quantityRemovalTypes.includes(
                adjustmentForm.type
            ) &&
            quantity >
                Number(item.quantity)
        ) {
            notify(
                "The quantity to remove is greater than the available stock."
            );

            return;
        }

        if (
            !adjustmentForm.date
        ) {
            notify(
                "Please select the adjustment date."
            );

            return;
        }

        if (
            adjustmentForm.type === "Stock Usage" &&
            item.expirationDate &&
            adjustmentForm.date > item.expirationDate
        ) {
            notify(
                "This inventory batch is expired. Record it as Expired stock instead of Stock Usage."
            );
            return;
        }

        if (
            !adjustmentForm.reason.trim()
        ) {
            notify(
                "Please enter the reason for the stock adjustment."
            );

            return;
        }

        const payload = {
            type: adjustmentForm.type,
            quantity,
            date: adjustmentForm.date,
            reason: adjustmentForm.reason.trim(),
            reference: adjustmentForm.reference.trim() || "No reference",
            supplier: adjustmentForm.supplier.trim() || item.supplier,
        };
        const idempotencyKey = stableIdempotencyKey(
            adjustmentRequestRef,
            payload,
            `inventory-stock-adjust:${item.id}`
        );

        adjustmentSubmittingRef.current = true;
        setAdjustmentSaving(true);

        try {
            const saved = await onAdjustStock(
                item.id,
                payload,
                idempotencyKey
            );

            if (saved === false) {
                return;
            }

            clearStableIdempotencyKey(adjustmentRequestRef);
            setAdjustmentForm({
                type: "Restock",
                quantity: "",
                date: getTodayDate(),
                reason: "",
                reference: "",
                supplier: item.supplier || "",
            });

            setActiveTab("history");
        } finally {
            adjustmentSubmittingRef.current = false;
            setAdjustmentSaving(false);
        }
    };

    return (
        <div
            className="inventory-modal-overlay"
            onMouseDown={onClose}
        >
            <div
                className="inventory-details-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="inventory-details-header">
                    <div className="inventory-details-title">
                        <span className="inventory-details-icon">
                            <span className="material-symbols-outlined">
                                inventory_2
                            </span>
                        </span>

                        <div>
                            <div className="inventory-details-code-line">
                                <h2>
                                    {item.name}
                                </h2>

                                <span>
                                    {
                                        item.itemCode
                                    }
                                </span>
                            </div>

                            <p>
                                {item.category} •{" "}
                                {item.location}
                            </p>
                        </div>
                    </div>

                    <div className="inventory-details-header-actions">
                        <span
                            className={`inventory-details-stock-status ${getStatusClass(
                                stockStatus
                            )}`}
                        >
                            {stockStatus}
                        </span>

                        <button
                            type="button"
                            onClick={onClose}
                            aria-label="Close inventory details"
                        >
                            <span className="material-symbols-outlined">
                                close
                            </span>
                        </button>
                    </div>
                </header>

                <nav className="inventory-detail-tabs">
                    {[
                        {
                            value: "overview",
                            label: "Overview",
                            icon: "dashboard",
                        },
                        {
                            value: "adjust",
                            label:
                                "Adjust Stock",
                            icon: "inventory",
                        },
                        {
                            value: "history",
                            label:
                                "Stock History",
                            icon: "history",
                        },
                    ].map((tab) => (
                        <button
                            type="button"
                            key={tab.value}
                            className={
                                activeTab ===
                                tab.value
                                    ? "active"
                                    : ""
                            }
                            onClick={() =>
                                setActiveTab(
                                    tab.value
                                )
                            }
                        >
                            <span className="material-symbols-outlined">
                                {tab.icon}
                            </span>

                            {tab.label}
                        </button>
                    ))}
                </nav>

                <div className="inventory-details-body">
                    {activeTab ===
                        "overview" && (
                        <>
                            <section className="inventory-overview-grid">
                                <div className="inventory-overview-card">
                                    <span className="material-symbols-outlined">
                                        stacked_bar_chart
                                    </span>

                                    <div>
                                        <small>
                                            Current Stock
                                        </small>

                                        <strong>
                                            {
                                                item.quantity
                                            }{" "}
                                            {item.unit}
                                        </strong>
                                    </div>
                                </div>

                                <div className="inventory-overview-card">
                                    <span className="material-symbols-outlined">
                                        warning
                                    </span>

                                    <div>
                                        <small>
                                            Reorder Level
                                        </small>

                                        <strong>
                                            {
                                                item.reorderLevel
                                            }{" "}
                                            {item.unit}
                                        </strong>
                                    </div>
                                </div>

                                <div className="inventory-overview-card">
                                    <span className="material-symbols-outlined">
                                        payments
                                    </span>

                                    <div>
                                        <small>
                                            Unit Cost
                                        </small>

                                        <strong>
                                            {formatCurrency(
                                                item.cost
                                            )}
                                        </strong>
                                    </div>
                                </div>

                                <div className="inventory-overview-card">
                                    <span className="material-symbols-outlined">
                                        sell
                                    </span>

                                    <div>
                                        <small>
                                            Unit Price
                                        </small>

                                        <strong>
                                            {formatCurrency(
                                                item.price
                                            )}
                                        </strong>
                                    </div>
                                </div>

                                <div className="inventory-overview-card">
                                    <span className="material-symbols-outlined">
                                        account_balance_wallet
                                    </span>

                                    <div>
                                        <small>
                                            Total Cost
                                        </small>

                                        <strong>
                                            {formatCurrency(
                                                Number(
                                                    item.quantity
                                                ) *
                                                    Number(
                                                        item.cost
                                                    )
                                            )}
                                        </strong>
                                    </div>
                                </div>

                                <div className="inventory-overview-card">
                                    <span className="material-symbols-outlined">
                                        store
                                    </span>

                                    <div>
                                        <small>
                                            Supplier
                                        </small>

                                        <strong>
                                            {
                                                item.supplier
                                            }
                                        </strong>
                                    </div>
                                </div>

                                <div className="inventory-overview-card">
                                    <span className="material-symbols-outlined">
                                        calendar_today
                                    </span>

                                    <div>
                                        <small>
                                            Date Acquired
                                        </small>

                                        <strong>
                                            {formatDate(
                                                item.dateAcquired
                                            )}
                                        </strong>
                                    </div>
                                </div>

                                <div className="inventory-overview-card">
                                    <span className="material-symbols-outlined">
                                        event_busy
                                    </span>

                                    <div>
                                        <small>
                                            Expiration Date
                                        </small>

                                        <strong>
                                            {formatDate(
                                                item.expirationDate
                                            )}
                                        </strong>
                                    </div>
                                </div>
                            </section>

                            <section className="inventory-details-section">
                                <div className="inventory-details-section-heading">
                                    <div>
                                        <h3>
                                            Item Information
                                        </h3>

                                        <p>
                                            Description,
                                            storage, and
                                            stock information
                                            for this item.
                                        </p>
                                    </div>
                                </div>

                                <div className="inventory-details-info-grid">
                                    <div>
                                        <small>
                                            Category
                                        </small>

                                        <strong>
                                            {
                                                item.category
                                            }
                                        </strong>
                                    </div>

                                    <div>
                                        <small>
                                            Unit
                                        </small>

                                        <strong>
                                            {item.unit}
                                        </strong>
                                    </div>

                                    <div>
                                        <small>
                                            Batch / Lot
                                        </small>

                                        <strong>
                                            {item.batchNumber || "—"}
                                        </strong>
                                    </div>

                                    <div>
                                        <small>
                                            Storage Location
                                        </small>

                                        <strong>
                                            {
                                                item.location
                                            }
                                        </strong>
                                    </div>

                                    <div>
                                        <small>
                                            Stock Status
                                        </small>

                                        <strong>
                                            {
                                                stockStatus
                                            }
                                        </strong>
                                    </div>
                                </div>

                                <div className="inventory-description-box">
                                    <strong>
                                        Description
                                    </strong>

                                    <p>
                                        {item.description ||
                                            "No description provided."}
                                    </p>
                                </div>

                                <div className="inventory-notes-box">
                                    <strong>
                                        Notes
                                    </strong>

                                    <p>
                                        {item.notes ||
                                            "No additional notes."}
                                    </p>
                                </div>
                            </section>
                        </>
                    )}

                    {activeTab ===
                        "adjust" && (
                        <section className="inventory-details-section">
                            <div className="inventory-details-section-heading">
                                <div>
                                    <h3>
                                        Stock Adjustment
                                    </h3>

                                    <p>
                                        Restock an item,
                                        record stock usage,
                                        remove damaged
                                        stock, or correct
                                        the quantity.
                                    </p>
                                </div>
                            </div>

                            <form
                                className="inventory-stock-form"
                                onSubmit={
                                    handleAdjustmentSubmit
                                }
                            >
                                <div className="inventory-form-grid">
                                    <div className="inventory-form-group">
                                        <label htmlFor="stockAdjustmentType">
                                            Adjustment Type
                                            <span>*</span>
                                        </label>

                                        <select
                                            id="stockAdjustmentType"
                                            name="type"
                                            value={
                                                adjustmentForm.type
                                            }
                                            onChange={
                                                handleAdjustmentChange
                                            }
                                            required
                                        >
                                            {stockAdjustmentTypes.map(
                                                (
                                                    type
                                                ) => (
                                                    <option
                                                        key={
                                                            type
                                                        }
                                                        value={
                                                            type
                                                        }
                                                    >
                                                        {
                                                            type
                                                        }
                                                    </option>
                                                )
                                            )}
                                        </select>
                                    </div>

                                    <div className="inventory-form-group">
                                        <label htmlFor="stockAdjustmentQuantity">
                                            {adjustmentForm.type ===
                                            "Set Exact Quantity"
                                                ? "New Exact Quantity"
                                                : "Adjustment Quantity"}

                                            <span>*</span>
                                        </label>

                                        <div className="inventory-unit-input">
                                            <input
                                                id="stockAdjustmentQuantity"
                                                name="quantity"
                                                type="number"
                                                min="0"
                                                step="0.01"
                                                placeholder="0"
                                                value={
                                                    adjustmentForm.quantity
                                                }
                                                onChange={
                                                    handleAdjustmentChange
                                                }
                                                required
                                            />

                                            <span>
                                                {
                                                    item.unit
                                                }
                                            </span>
                                        </div>
                                    </div>

                                    <div className="inventory-form-group">
                                        <label htmlFor="stockAdjustmentDate">
                                            Adjustment Date
                                            <span>*</span>
                                        </label>

                                        <input
                                            id="stockAdjustmentDate"
                                            name="date"
                                            type="date"
                                            value={
                                                adjustmentForm.date
                                            }
                                            onChange={
                                                handleAdjustmentChange
                                            }
                                            required
                                        />
                                    </div>

                                    <div className="inventory-form-group">
                                        <label htmlFor="stockReference">
                                            Reference
                                        </label>

                                        <input
                                            id="stockReference"
                                            name="reference"
                                            type="text"
                                            placeholder="Example: Delivery Receipt 1045"
                                            value={
                                                adjustmentForm.reference
                                            }
                                            onChange={
                                                handleAdjustmentChange
                                            }
                                        />
                                    </div>

                                    <div className="inventory-form-group full-width">
                                        <label htmlFor="stockSupplier">
                                            Supplier or
                                            Source
                                        </label>

                                        <input
                                            id="stockSupplier"
                                            name="supplier"
                                            type="text"
                                            value={
                                                adjustmentForm.supplier
                                            }
                                            onChange={
                                                handleAdjustmentChange
                                            }
                                        />
                                    </div>
                                </div>

                                <div className="inventory-stock-preview">
                                    <div>
                                        <small>
                                            Current
                                            Quantity
                                        </small>

                                        <strong>
                                            {
                                                item.quantity
                                            }{" "}
                                            {item.unit}
                                        </strong>
                                    </div>

                                    <span className="material-symbols-outlined">
                                        arrow_forward
                                    </span>

                                    <div>
                                        <small>
                                            New Quantity
                                        </small>

                                        <strong>
                                            {
                                                projectedQuantity
                                            }{" "}
                                            {item.unit}
                                        </strong>
                                    </div>
                                </div>

                                <div className="inventory-form-group">
                                    <label htmlFor="stockAdjustmentReason">
                                        Reason
                                        <span>*</span>
                                    </label>

                                    <textarea
                                        id="stockAdjustmentReason"
                                        name="reason"
                                        rows="4"
                                        placeholder="Explain why the inventory quantity is being changed..."
                                        value={
                                            adjustmentForm.reason
                                        }
                                        onChange={
                                            handleAdjustmentChange
                                        }
                                        required
                                    />
                                </div>

                                <div className="inventory-stock-form-footer">
                                    <button
                                        type="submit"
                                        disabled={adjustmentSaving}
                                        aria-busy={adjustmentSaving}
                                    >
                                        <span className="material-symbols-outlined">
                                            {adjustmentSaving ? "progress_activity" : "save"}
                                        </span>

                                        {adjustmentSaving
                                            ? "Saving Stock Adjustment..."
                                            : "Save Stock Adjustment"}
                                    </button>
                                </div>
                            </form>
                        </section>
                    )}

                    {activeTab ===
                        "history" && (
                        <section className="inventory-details-section">
                            <div className="inventory-details-section-heading">
                                <div>
                                    <h3>
                                        Stock Movement
                                        History
                                    </h3>

                                    <p>
                                        Review restocking,
                                        usage, damage,
                                        expiration, and
                                        quantity-correction
                                        records.
                                    </p>
                                </div>

                                <span className="inventory-history-count">
                                    {
                                        stockHistory.length
                                    }{" "}
                                    {stockHistory.length ===
                                    1
                                        ? "record"
                                        : "records"}
                                </span>
                            </div>

                            <div className="inventory-history-list">
                                {stockHistory.length >
                                0 ? (
                                    stockHistory.map(
                                        (
                                            record
                                        ) => (
                                            <article
                                                className="inventory-history-item"
                                                key={
                                                    record.id
                                                }
                                            >
                                                <span
                                                    className={`inventory-history-icon ${getStatusClass(
                                                        record.type
                                                    )}`}
                                                >
                                                    <span className="material-symbols-outlined">
                                                        {record.type === "Set Exact Quantity"
                                                            ? "edit"
                                                            : Number(record.newQuantity) >=
                                                              Number(record.previousQuantity)
                                                            ? "add_box"
                                                            : "remove_circle"}
                                                    </span>
                                                </span>

                                                <div className="inventory-history-main">
                                                    <div className="inventory-history-title-line">
                                                        <strong>
                                                            {
                                                                record.type
                                                            }
                                                        </strong>

                                                        <span>
                                                            {formatDate(
                                                                record.date
                                                            )}
                                                        </span>
                                                    </div>

                                                    <p>
                                                        {
                                                            record.reason
                                                        }
                                                    </p>

                                                    <small>
                                                        Reference:{" "}
                                                        {record.reference ||
                                                            "No reference"}{" "}
                                                        • Source:{" "}
                                                        {record.supplier ||
                                                            "Not specified"}
                                                    </small>
                                                </div>

                                                <div className="inventory-history-quantity">
                                                    <small>
                                                        Quantity
                                                    </small>

                                                    <strong>
                                                        {
                                                            record.previousQuantity
                                                        }{" "}
                                                        →{" "}
                                                        {
                                                            record.newQuantity
                                                        }{" "}
                                                        {
                                                            item.unit
                                                        }
                                                    </strong>

                                                    <span>
                                                        {record.type === "Set Exact Quantity"
                                                            ? "="
                                                            : Number(record.newQuantity) >=
                                                              Number(record.previousQuantity)
                                                            ? "+"
                                                            : "-"}

                                                        {
                                                            record.quantity
                                                        }
                                                    </span>
                                                </div>
                                            </article>
                                        )
                                    )
                                ) : (
                                    <div className="inventory-empty-history">
                                        <span className="material-symbols-outlined">
                                            history
                                        </span>

                                        <p>
                                            No stock
                                            movement
                                            records are
                                            available.
                                        </p>
                                    </div>
                                )}
                            </div>
                        </section>
                    )}
                </div>

                <footer className="inventory-details-footer">
                    <button
                        type="button"
                        onClick={onClose}
                    >
                        Close
                    </button>
                </footer>
            </div>
        </div>
    );
} 
