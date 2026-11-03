"use client";

import { useState } from "react";

import {
    notifySuccess,
    notifyWarning,
    confirmAction,
} from "../../../context/NotificationContext.jsx";

import {
    addTimelineEntry,
    getProductionTargets,
    logAudit,
    saveProductionTargets,
} from "../../../services/farmIntelligenceService.js";

// Simple money display for production totals
function formatCurrency(value) {
    return Number(value || 0).toLocaleString(
        "en-PH",
        {
            style: "currency",
            currency: "PHP",
            maximumFractionDigits: 0,
        }
    );
}

// Add all recorded costs
function totalCosts(costs = {}) {
    return Object.values(costs).reduce(
        (sum, value) => sum + Number(value || 0),
        0
    );
}

// Production targets, actual output, costs, and estimated profit
export default function ProductionPanel({ canEdit }) {
    const [records, setRecords] =
        useState(getProductionTargets);

    const [form, setForm] = useState({
        recordType: "Crop",
        recordName: "",
        period: "",
        unit: "kg",
        target: "",
        actual: "",
        sellingPrice: "",
        seeds: "",
        fertilizer: "",
        pesticideMedicine: "",
        feed: "",
        labor: "",
        waterUtilities: "",
        other: "",
    });

    const saveRecords = (nextRecords) => {
        setRecords(nextRecords);
        saveProductionTargets(nextRecords);
    };

    const handleChange = (event) => {
        const { name, value } =
            event.target;

        setForm((current) => ({
            ...current,
            [name]: value,
        }));
    };

    const handleSubmit = (event) => {
        event.preventDefault();

        if (!canEdit) {
            notifyWarning(
                "Your account can view production analytics but cannot add production targets."
            );
            return;
        }

        const nextRecord = {
            id: `target-${Date.now()}`,
            recordType: form.recordType,
            recordName: form.recordName.trim(),
            period: form.period.trim(),
            unit: form.unit.trim() || "units",
            target: Number(form.target || 0),
            actual: Number(form.actual || 0),
            sellingPrice: Number(
                form.sellingPrice || 0
            ),
            costs: {
                seeds: Number(form.seeds || 0),
                fertilizer: Number(
                    form.fertilizer || 0
                ),
                pesticideMedicine: Number(
                    form.pesticideMedicine || 0
                ),
                feed: Number(form.feed || 0),
                labor: Number(form.labor || 0),
                waterUtilities: Number(
                    form.waterUtilities || 0
                ),
                other: Number(form.other || 0),
            },
        };

        if (!nextRecord.recordName) {
            notifyWarning(
                "Please enter a crop, livestock, or production record name."
            );
            return;
        }

        saveRecords([
            nextRecord,
            ...records,
        ]);

        logAudit({
            action: "Added production target",
            module: form.recordType,
            recordName:
                nextRecord.recordName,
            entityId: nextRecord.id,
            details:
                `Target ${nextRecord.target} ${nextRecord.unit}; actual ${nextRecord.actual} ${nextRecord.unit}.`,
        });

        addTimelineEntry({
            module: form.recordType,
            recordName:
                nextRecord.recordName,
            entityId: nextRecord.id,
            title: "Production target recorded",
            details:
                `${nextRecord.period}: ${nextRecord.target} ${nextRecord.unit} target.`,
            icon: "target",
        });

        setForm((current) => ({
            ...current,
            recordName: "",
            period: "",
            target: "",
            actual: "",
            sellingPrice: "",
            seeds: "",
            fertilizer: "",
            pesticideMedicine: "",
            feed: "",
            labor: "",
            waterUtilities: "",
            other: "",
        }));

        notifySuccess(
            "Production target and cost record added."
        );
    };

    const removeRecord = async (record) => {
        if (!canEdit) {
            return;
        }

        const confirmed =
            await confirmAction({
                title: "Remove Production Record",
                message:
                    `Remove the production target for ${record.recordName}?`,
                type: "warning",
                confirmText: "Remove",
                cancelText: "Cancel",
            });

        if (!confirmed) {
            return;
        }

        saveRecords(
            records.filter(
                (item) =>
                    item.id !== record.id
            )
        );

        logAudit({
            action: "Removed production target",
            module: record.recordType,
            recordName: record.recordName,
            entityId: record.id,
        });
    };

    return (
        <div className="fi-stack">
            <section className="fi-card">
                <div className="fi-section-heading">
                    <div>
                        <h3>
                            Target vs Actual Production
                        </h3>
                        <p>
                            Compare production goals, actual output,
                            revenue, cost, and estimated profit.
                        </p>
                    </div>
                </div>

                <div className="fi-production-list">
                    {records.map((record) => {
                        const achievement =
                            record.target > 0
                                ? Math.round(
                                      (record.actual /
                                          record.target) *
                                          100
                                  )
                                : 0;

                        const costs = totalCosts(
                            record.costs
                        );

                        const revenue =
                            Number(
                                record.actual
                            ) *
                            Number(
                                record.sellingPrice
                            );

                        const profit =
                            revenue - costs;

                        return (
                            <article
                                key={record.id}
                                className="fi-production-card"
                            >
                                <div className="fi-production-main">
                                    <span className="fi-module-icon">
                                        <span className="material-symbols-outlined">
                                            {record.recordType ===
                                            "Crop"
                                                ? "grass"
                                                : "pets"}
                                        </span>
                                    </span>

                                    <div>
                                        <h4>
                                            {
                                                record.recordName
                                            }
                                        </h4>
                                        <p>
                                            {record.period}
                                            {" • "}
                                            {record.recordType}
                                        </p>
                                    </div>
                                </div>

                                <div className="fi-production-metrics">
                                    <div>
                                        <small>Target</small>
                                        <strong>
                                            {record.target.toLocaleString()}{" "}
                                            {record.unit}
                                        </strong>
                                    </div>

                                    <div>
                                        <small>Actual</small>
                                        <strong>
                                            {record.actual.toLocaleString()}{" "}
                                            {record.unit}
                                        </strong>
                                    </div>

                                    <div>
                                        <small>Achievement</small>
                                        <strong>
                                            {achievement}%
                                        </strong>
                                    </div>

                                    <div>
                                        <small>Total Cost</small>
                                        <strong>
                                            {formatCurrency(
                                                costs
                                            )}
                                        </strong>
                                    </div>

                                    <div>
                                        <small>Revenue</small>
                                        <strong>
                                            {formatCurrency(
                                                revenue
                                            )}
                                        </strong>
                                    </div>

                                    <div>
                                        <small>
                                            Estimated Profit
                                        </small>
                                        <strong
                                            className={
                                                profit >= 0
                                                    ? "positive"
                                                    : "negative"
                                            }
                                        >
                                            {formatCurrency(
                                                profit
                                            )}
                                        </strong>
                                    </div>
                                </div>

                                <div className="fi-achievement-track">
                                    <span
                                        style={{
                                            width: `${Math.min(
                                                achievement,
                                                100
                                            )}%`,
                                        }}
                                    />
                                </div>

                                {canEdit && (
                                    <button
                                        type="button"
                                        className="fi-icon-button danger"
                                        onClick={() =>
                                            removeRecord(
                                                record
                                            )
                                        }
                                        title="Remove production record"
                                    >
                                        <span className="material-symbols-outlined">
                                            delete
                                        </span>
                                    </button>
                                )}
                            </article>
                        );
                    })}
                </div>
            </section>

            <section className="fi-card">
                <div className="fi-section-heading">
                    <div>
                        <h3>
                            Add Production & Cost Record
                        </h3>
                        <p>
                            Basic profitability only. This is not a full
                            accounting module.
                        </p>
                    </div>
                </div>

                <form
                    className="fi-form-grid"
                    onSubmit={handleSubmit}
                >
                    <label>
                        <span>Record Type</span>
                        <select
                            name="recordType"
                            value={form.recordType}
                            onChange={handleChange}
                            disabled={!canEdit}
                        >
                            <option>Crop</option>
                            <option>Livestock</option>
                        </select>
                    </label>

                    <label>
                        <span>Record Name *</span>
                        <input
                            name="recordName"
                            value={form.recordName}
                            onChange={handleChange}
                            placeholder="Example: Yellow Corn"
                            disabled={!canEdit}
                        />
                    </label>

                    <label>
                        <span>Period *</span>
                        <input
                            name="period"
                            value={form.period}
                            onChange={handleChange}
                            placeholder="Example: 2026 Wet Season"
                            disabled={!canEdit}
                        />
                    </label>

                    <label>
                        <span>Unit</span>
                        <input
                            name="unit"
                            value={form.unit}
                            onChange={handleChange}
                            placeholder="kg"
                            disabled={!canEdit}
                        />
                    </label>

                    <label>
                        <span>Target</span>
                        <input
                            type="number"
                            min="0"
                            name="target"
                            value={form.target}
                            onChange={handleChange}
                            disabled={!canEdit}
                        />
                    </label>

                    <label>
                        <span>Actual</span>
                        <input
                            type="number"
                            min="0"
                            name="actual"
                            value={form.actual}
                            onChange={handleChange}
                            disabled={!canEdit}
                        />
                    </label>

                    <label>
                        <span>Selling Value / Unit</span>
                        <div className="fi-unit-field">
                            <span>₱</span>
                            <input
                                type="number"
                                min="0"
                                name="sellingPrice"
                                value={form.sellingPrice}
                                onChange={handleChange}
                                disabled={!canEdit}
                            />
                        </div>
                    </label>

                    <div className="fi-form-divider">
                        Cost Breakdown
                    </div>

                    {[
                        ["seeds", "Seeds / Planting Materials"],
                        ["fertilizer", "Fertilizer"],
                        [
                            "pesticideMedicine",
                            "Pesticide / Medicine",
                        ],
                        ["feed", "Feed"],
                        ["labor", "Labor"],
                        ["waterUtilities", "Water / Utilities"],
                        ["other", "Other Cost"],
                    ].map(([name, label]) => (
                        <label key={name}>
                            <span>{label}</span>
                            <div className="fi-unit-field">
                                <span>₱</span>
                                <input
                                    type="number"
                                    min="0"
                                    name={name}
                                    value={form[name]}
                                    onChange={handleChange}
                                    disabled={!canEdit}
                                />
                            </div>
                        </label>
                    ))}

                    {canEdit && (
                        <div className="fi-form-actions">
                            <button
                                type="submit"
                                className="fi-primary-button"
                            >
                                <span className="material-symbols-outlined">
                                    save
                                </span>
                                Save Production Record
                            </button>
                        </div>
                    )}
                </form>
            </section>
        </div>
    );
}
