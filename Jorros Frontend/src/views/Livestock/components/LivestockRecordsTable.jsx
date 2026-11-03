"use client";

function formatDate(dateValue) {
    if (!dateValue) return "—";
    const [year, month, day] = dateValue.split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

function healthParts(animal) {
    return [
        ["Healthy", Number(animal.healthyQuantity || 0), "healthy"],
        ["At Risk", Number(animal.atRiskQuantity || 0), "at-risk"],
        ["Sick", Number(animal.sickQuantity || 0), "sick"],
        ["Treatment", Number(animal.underTreatmentQuantity || 0), "under-treatment"],
    ].filter(([, count]) => count > 0);
}

function LivestockRecordsTable({
    livestock,
    filteredLivestock,
    onAdd,
    onManagePens,
    onView,
    onEdit,
    onManage,
    onArchive,
}) {
    return (
        <>
            <section className="livestock-action-row">
                <div>
                    <h2>Livestock Overview</h2>
                    <p>{filteredLivestock.length} livestock batch records found</p>
                </div>

                <div className="livestock-action-buttons">
                    <button type="button" className="livestock-pen-button" onClick={onManagePens}>
                        <span className="material-symbols-outlined">fence</span>
                        Manage Pens
                    </button>
                    <button type="button" className="livestock-add-button" onClick={onAdd}>
                        <span className="material-symbols-outlined">add</span>
                        Add Livestock
                    </button>
                </div>
            </section>

            <section className="livestock-table-card">
                <div className="livestock-table-wrapper">
                    <table className="livestock-table">
                        <colgroup>
                            <col className="livestock-col-id" />
                            <col className="livestock-col-record" />
                            <col className="livestock-col-type" />
                            <col className="livestock-col-count" />
                            <col className="livestock-col-health" />
                            <col className="livestock-col-age" />
                            <col className="livestock-col-location" />
                            <col className="livestock-col-actions" />
                        </colgroup>
                        <thead>
                            <tr>
                                <th>Batch ID</th>
                                <th>Record</th>
                                <th>Type / Breed</th>
                                <th>Count / Weight</th>
                                <th>Health Breakdown</th>
                                <th>Production / Growth</th>
                                <th>Current Pen / Checkup</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredLivestock.length > 0 ? (
                                filteredLivestock.map((animal) => (
                                    <tr key={animal.id}>
                                        <td>
                                            <strong className="animal-id">{animal.animalId}</strong>
                                            <span className="livestock-record-type-badge batch">Aggregate</span>
                                        </td>
                                        <td>
                                            <div className="animal-name-cell">
                                                <span className={`animal-type-icon ${String(animal.type || "").toLowerCase()}`}>
                                                    <span className="material-symbols-outlined">pets</span>
                                                </span>
                                                <div>
                                                    <strong>{animal.recordName}</strong>
                                                    <small>{animal.sex} · {animal.maleQuantity}M / {animal.femaleQuantity}F{animal.unknownSexQuantity ? ` / ${animal.unknownSexQuantity}U` : ""}</small>
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            <strong>{animal.type}</strong>
                                            <small className="table-subtext">{animal.breed}</small>
                                        </td>
                                        <td>
                                            <div className="livestock-stacked-cell">
                                                <strong>{animal.quantity} head</strong>
                                                <small>{Number(animal.weight || 0).toFixed(2)} kg avg</small>
                                                <small>{Number(animal.minWeight || animal.weight || 0).toFixed(2)}–{Number(animal.maxWeight || animal.weight || 0).toFixed(2)} kg</small>
                                            </div>
                                        </td>
                                        <td>
                                            <div className="livestock-health-breakdown">
                                                {healthParts(animal).map(([label, count, className]) => (
                                                    <span key={label} className={`livestock-health-mini ${className}`}>
                                                        {count} {label}
                                                    </span>
                                                ))}
                                            </div>
                                        </td>
                                        <td>
                                            <div className="livestock-stacked-cell">
                                                <strong>{animal.productionPurpose || "General"}</strong>
                                                <small>{animal.growthStatus}</small>
                                            </div>
                                        </td>
                                        <td>
                                            <div className="livestock-stacked-cell">
                                                <strong>{animal.penLocation}</strong>
                                                <small>Last: {formatDate(animal.lastCheckup)}</small>
                                            </div>
                                        </td>
                                        <td>
                                            <div className="livestock-row-actions">
                                                <button type="button" title="View livestock details" onClick={() => onView(animal)}>
                                                    <span className="material-symbols-outlined">visibility</span>
                                                </button>
                                                <button type="button" title="Edit batch" onClick={() => onEdit(animal)}>
                                                    <span className="material-symbols-outlined">edit</span>
                                                </button>
                                                <button type="button" title="Transfer or split batch" onClick={() => onManage(animal)}>
                                                    <span className="material-symbols-outlined">move_down</span>
                                                </button>
                                                <button type="button" className="archive" title="Archive livestock" onClick={() => onArchive(animal.id)}>
                                                    <span className="material-symbols-outlined">archive</span>
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan="8" className="livestock-empty-table">
                                        <span className="material-symbols-outlined">search_off</span>
                                        <p>No livestock records match the selected filters.</p>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
                <div className="livestock-table-footer">
                    <span>Showing {filteredLivestock.length} of {livestock.length} livestock batch records</span>
                </div>
            </section>
        </>
    );
}

export default LivestockRecordsTable;
