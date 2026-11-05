import { WORK_TYPES, workTypeLabel, eventDomain, taskCategoryUpdate } from "../../../services/eventPlanning.js";
import { PersonalNameFields, PersonalAddressFields } from "../../../components/PersonalDetails/PersonalDetails.jsx";
import { composeFullName } from "../../../components/PersonalDetails/personalDetails.js";
import { MonitoringObservationFields } from "../../../components/Monitoring/Monitoring.jsx";
import EvidencePhotoField from "../../../components/EvidencePhoto/EvidencePhoto.jsx";
import WeeklyScheduleEditor from "../../../components/WeeklyScheduleEditor/WeeklyScheduleEditor.jsx";
import { statusClass } from "./AssignmentsPanel.jsx";
import {
    employeePositionLabel,
    suggestEmployeeUsername,
    today,
} from "../taskManagementUtils.js";

function TaskManagementModals({
    archiveReason,
    assistedCorrectionMode,
    assistedEmployeeOptions,
    assistedForm,
    assistedIsCropHarvest,
    assistedResourceItems,
    assistedSaving,
    assistedSelectedInventoryItem,
    assistedTask,
    changePrimaryPosition,
    closeAssistedModal,
    closeEmployeeActionModal,
    closeEmployeeModal,
    closeReassignModal,
    closeTaskModal,
    closeViewEmployeeModal,
    editingEmployeeId,
    employeeAction,
    employeeAssignmentOptions,
    employeeAssignmentsLoaded,
    employeeAssignmentsLoading,
    employeeForm,
    employees,
    filteredPositionGroups,
    inventoryItems,
    manualTaskResourceItems,
    openEditEmployee,
    otherReassignCandidates,
    performEmployeeAction,
    performTaskReassignment,
    positionGroups,
    positionSearch,
    reassignCandidates,
    reassignEmployeeId,
    reassignProfile,
    reassignSaving,
    reassignSearch,
    reassignTask,
    recommendedReassignCandidates,
    saveEmployeeProfile,
    saveTask,
    selectedAdditionalPositions,
    selectedPrimaryPosition,
    selectedTaskInventoryItem,
    setArchiveReason,
    setAssistedForm,
    setEmployeeForm,
    setPositionSearch,
    setReassignEmployeeId,
    setReassignSearch,
    setTaskForm,
    showEmployeeForm,
    showTaskForm,
    submitAssistedWork,
    taskAssignmentStockError,
    taskForm,
    taskSaving,
    existingTaskId,
    taskSourceOptions,
    tasks,
    toggleAdditionalPosition,
    toggleEmployeeWorkAssignment,
    viewEmployee,
    viewEmployeeAssignments,
    viewEmployeeLoading,
    viewEmployeeTasks,
}) {
    return (
        <>
            {showEmployeeForm && (
                <div
                    className="workforce-modal-overlay"
                    onMouseDown={(event) => {
                        if (event.target === event.currentTarget) closeEmployeeModal();
                    }}
                >
                    <div
                        className="workforce-task-modal workforce-employee-modal"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="add-employee-modal-title"
                        onMouseDown={(event) => event.stopPropagation()}
                    >
                        <header className="workforce-modal-header">
                            <div>
                                <h2 id="add-employee-modal-title">{editingEmployeeId ? "Edit Employee" : "Add Employee"}</h2>
                                <p>{editingEmployeeId ? "Update employee information, farm positions, assignments, and login access." : "Create an employee profile for farm work. A linked Employee login is created by default for My Tasks."}</p>
                            </div>
                            <button type="button" className="workforce-modal-close" onClick={closeEmployeeModal} aria-label="Close add employee modal">
                                <span className="material-symbols-outlined">close</span>
                            </button>
                        </header>

                        <form className="workforce-modal-form" onSubmit={saveEmployeeProfile}>
                            <section className="workforce-modal-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">badge</span>
                                    <div>
                                        <h3>Employee Information</h3>
                                        <p>Record the employee's contact information. Login credentials are managed separately below.</p>
                                    </div>
                                </div>

                                <div className="workforce-modal-form-grid">
                                    <PersonalNameFields value={employeeForm.personal_details} legacyFullName={editingEmployeeId ? employeeForm.full_name : ""} isNew={!editingEmployeeId}
                                        onChange={(details) => setEmployeeForm((current) => {
                                            const fullName = composeFullName(details, current.full_name);
                                            return { ...current, personal_details: details, full_name: fullName, login_username: (!current.has_login_account && current.create_login_account && (!current.login_username || current.login_username === suggestEmployeeUsername(current.full_name))) ? suggestEmployeeUsername(fullName) : current.login_username };
                                        })}/>
                                    <div className="workforce-field">
                                        <label htmlFor="employee-contact">Contact Number</label>
                                        <input id="employee-contact" placeholder="e.g. 09XXXXXXXXX" value={employeeForm.contact_number} onChange={(e)=>setEmployeeForm({...employeeForm,contact_number:e.target.value})}/>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="employee-email">Email <span className="field-optional">Optional</span></label>
                                        <input id="employee-email" type="email" placeholder="e.g. john@example.com" value={employeeForm.email} onChange={(e)=>setEmployeeForm({...employeeForm,email:e.target.value})}/>
                                    </div>
                                    <PersonalAddressFields value={employeeForm.personal_details} legacyAddress={employeeForm.address} onChange={(details) => setEmployeeForm((current) => ({ ...current, personal_details: details }))}/>

                                </div>
                            </section>

                            <section className="workforce-modal-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">agriculture</span>
                                    <div>
                                        <h3>Farm Positions & Employment</h3>
                                        <p>Choose one primary job and up to four additional farm jobs. The employee can receive assignments for any selected position.</p>
                                    </div>
                                </div>

                                <div className="workforce-modal-form-grid">
                                    <div className="workforce-field full">
                                        <label htmlFor="employee-primary-position">Primary Position <span className="required-mark">*</span></label>
                                        <select id="employee-primary-position" required value={employeeForm.primary_position_id} onChange={(e)=>changePrimaryPosition(e.target.value)}>
                                            <option value="">Select the employee's main farm position</option>
                                            {Object.entries(positionGroups).map(([category, items]) => (
                                                <optgroup key={category} label={category}>
                                                    {items.map((position) => <option key={position.id} value={position.id}>{position.name}</option>)}
                                                </optgroup>
                                            ))}
                                        </select>
                                        {selectedPrimaryPosition && <div className="position-helper">Primary: <strong>{selectedPrimaryPosition.name}</strong> · {selectedPrimaryPosition.category}</div>}
                                    </div>

                                    <div className="workforce-field full">
                                        <label>Additional Positions <span className="field-optional">Optional · up to 4</span></label>
                                        <details className="employee-position-picker">
                                            <summary>
                                                <span>{selectedAdditionalPositions.length ? `${selectedAdditionalPositions.length} additional position${selectedAdditionalPositions.length === 1 ? "" : "s"} selected` : "Select additional farm positions"}</span>
                                                <span className="material-symbols-outlined">expand_more</span>
                                            </summary>
                                            <div className="employee-position-picker-panel">
                                                <div className="position-search-wrap">
                                                    <span className="material-symbols-outlined">search</span>
                                                    <input type="search" placeholder="Search farm positions…" value={positionSearch} onChange={(e)=>setPositionSearch(e.target.value)}/>
                                                </div>
                                                <div className="position-picker-count">
                                                    {1 + selectedAdditionalPositions.length} of 5 total positions selected
                                                </div>
                                                <div className="position-options-scroll">
                                                    {Object.entries(filteredPositionGroups).map(([category, items]) => (
                                                        <div className="position-option-group" key={category}>
                                                            <div className="position-option-group-title">{category}</div>
                                                            {items.map((position) => {
                                                                const id = String(position.id);
                                                                const isPrimary = id === String(employeeForm.primary_position_id);
                                                                const checked = employeeForm.additional_position_ids.includes(id);
                                                                const disabled = isPrimary || (!checked && employeeForm.additional_position_ids.length >= 4);
                                                                return (
                                                                    <label key={position.id} className={`position-option ${isPrimary ? "primary-option" : ""} ${disabled && !isPrimary ? "disabled" : ""}`}>
                                                                        <input type="checkbox" checked={checked || isPrimary} disabled={disabled} onChange={()=>toggleAdditionalPosition(position.id)}/>
                                                                        <span>
                                                                            <strong>{position.name}</strong>
                                                                            {isPrimary && <small>Primary position</small>}
                                                                        </span>
                                                                    </label>
                                                                );
                                                            })}
                                                        </div>
                                                    ))}
                                                    {!Object.keys(filteredPositionGroups).length && <div className="position-no-results">No farm positions match your search.</div>}
                                                </div>
                                            </div>
                                        </details>
                                        {!!selectedAdditionalPositions.length && (
                                            <div className="employee-position-chips position-selection-chips">
                                                {selectedAdditionalPositions.map((position) => (
                                                    <button type="button" key={position.id} className="employee-position-chip removable" onClick={()=>toggleAdditionalPosition(position.id)} title="Remove position">
                                                        {position.name}
                                                        <span className="material-symbols-outlined">close</span>
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </div>

                                    <div className="workforce-field">
                                        <label htmlFor="employee-date-hired">Date Hired</label>
                                        <input id="employee-date-hired" type="date" value={employeeForm.date_hired} onChange={(e)=>setEmployeeForm((current)=>({...current,date_hired:e.target.value,weekly_schedule:{...current.weekly_schedule,effective_from:(!editingEmployeeId || current.schedule_needs_setup) ? (e.target.value || today()) : current.weekly_schedule.effective_from}}))}/>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="employee-employment-type">Employment Type</label>
                                        <select id="employee-employment-type" value={employeeForm.employment_type} onChange={(e)=>setEmployeeForm({...employeeForm,employment_type:e.target.value})}>
                                            {["Regular","Part-time","Seasonal","Contract","Temporary","On-call"].map((type)=><option key={type}>{type}</option>)}
                                        </select>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="employee-status">Employment Status</label>
                                        <select id="employee-status" value={employeeForm.employment_status} onChange={(e)=>setEmployeeForm({...employeeForm,employment_status:e.target.value})}>
                                            {["Active","On Leave","Inactive"].map((status)=><option key={status}>{status}</option>)}
                                        </select>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="employee-assigned-area">Usual Farm Area</label>
                                        <input id="employee-assigned-area" placeholder="e.g. Field A, Goat Pens, General Farm" value={employeeForm.assigned_area} onChange={(e)=>setEmployeeForm({...employeeForm,assigned_area:e.target.value})}/>
                                    </div>
                                    <div className="workforce-field full">
                                        <label htmlFor="employee-skills">Skills / Specializations</label>
                                        <textarea id="employee-skills" placeholder="e.g. goat handling, crop irrigation, machinery operation, vaccination assistance" value={employeeForm.skills} onChange={(e)=>setEmployeeForm({...employeeForm,skills:e.target.value})}/>
                                    </div>
                                </div>
                            </section>

                            <section className="workforce-modal-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">calendar_month</span>
                                    <div>
                                        <h3>Weekly Work Schedule</h3>
                                        <p>Set Working Days, Rest Days, shift hours, effective dates, and the configured backup employee. Rest days are part of the employee schedule, not a separate Task Management tab.</p>
                                    </div>
                                </div>
                                <WeeklyScheduleEditor
                                    value={employeeForm.weekly_schedule}
                                    onChange={(weekly_schedule)=>setEmployeeForm((current)=>({...current,weekly_schedule}))}
                                    employees={employees}
                                    employeeId={editingEmployeeId}
                                    needsSetup={Boolean(employeeForm.schedule_needs_setup)}
                                />
                            </section>

                            {editingEmployeeId && (
                                <section className="workforce-modal-section employee-current-assignments-section">
                                    <div className="workforce-modal-section-title">
                                        <span className="material-symbols-outlined">location_on</span>
                                        <div>
                                            <h3>Current Farm Assignments</h3>
                                            <p>Change the crop fields and livestock records this employee normally cares for. Existing task history is not changed.</p>
                                        </div>
                                    </div>

                                    {employeeAssignmentsLoading ? (
                                        <div className="workforce-inline-loading">Loading current farm assignments…</div>
                                    ) : !employeeAssignmentsLoaded ? (
                                        <div className="workforce-assignment-load-error">Current assignments could not be loaded. Profile changes can still be saved without changing farm assignments.</div>
                                    ) : (
                                        <>
                                            <div className="work-assignment-notice">
                                                <span className="material-symbols-outlined">info</span>
                                                Selecting a record currently assigned to another employee will move that current assignment to this employee. Historical tasks remain with the employee who originally performed or received them.
                                            </div>
                                            <div className="employee-work-assignment-grid">
                                                <div className="employee-work-assignment-panel">
                                                    <div className="employee-work-assignment-heading">
                                                        <span className="material-symbols-outlined">psychiatry</span>
                                                        <div>
                                                            <strong>Crop / Field Assignments</strong>
                                                            <small>{employeeForm.crop_assignment_ids.length} selected</small>
                                                        </div>
                                                    </div>
                                                    <div className="employee-work-assignment-list">
                                                        {employeeAssignmentOptions.crops.length ? employeeAssignmentOptions.crops.map((item) => {
                                                            const value = String(item.id);
                                                            const checked = employeeForm.crop_assignment_ids.includes(value);
                                                            const belongsToOther = item.assigned_employee_id && !item.is_assigned_to_employee;
                                                            return (
                                                                <label key={`crop-${item.id}`} className={`employee-work-assignment-option ${checked ? "selected" : ""}`}>
                                                                    <input type="checkbox" checked={checked} onChange={()=>toggleEmployeeWorkAssignment("crop_assignment_ids", item.id)}/>
                                                                    <span className="employee-work-assignment-copy">
                                                                        <strong>{item.name} <small>{item.record_code}</small></strong>
                                                                        <span>{item.location || "No field"}{item.detail ? ` • ${item.detail}` : ""}</span>
                                                                        {belongsToOther && <em>Currently assigned to {item.assigned_employee_name || "another employee"}</em>}
                                                                    </span>
                                                                </label>
                                                            );
                                                        }) : <div className="employee-work-assignment-empty">No active crop records available.</div>}
                                                    </div>
                                                </div>

                                                <div className="employee-work-assignment-panel">
                                                    <div className="employee-work-assignment-heading">
                                                        <span className="material-symbols-outlined">pets</span>
                                                        <div>
                                                            <strong>Livestock / Pen Assignments</strong>
                                                            <small>{employeeForm.livestock_assignment_ids.length} selected</small>
                                                        </div>
                                                    </div>
                                                    <div className="employee-work-assignment-list">
                                                        {employeeAssignmentOptions.livestock.length ? employeeAssignmentOptions.livestock.map((item) => {
                                                            const value = String(item.id);
                                                            const checked = employeeForm.livestock_assignment_ids.includes(value);
                                                            const belongsToOther = item.assigned_employee_id && !item.is_assigned_to_employee;
                                                            return (
                                                                <label key={`livestock-${item.id}`} className={`employee-work-assignment-option ${checked ? "selected" : ""}`}>
                                                                    <input type="checkbox" checked={checked} onChange={()=>toggleEmployeeWorkAssignment("livestock_assignment_ids", item.id)}/>
                                                                    <span className="employee-work-assignment-copy">
                                                                        <strong>{item.name} <small>{item.record_code}</small></strong>
                                                                        <span>{item.location || "No pen"}{item.detail ? ` • ${item.detail}` : ""}</span>
                                                                        {belongsToOther && <em>Currently assigned to {item.assigned_employee_name || "another employee"}</em>}
                                                                    </span>
                                                                </label>
                                                            );
                                                        }) : <div className="employee-work-assignment-empty">No active livestock records available.</div>}
                                                    </div>
                                                </div>
                                            </div>
                                        </>
                                    )}
                                </section>
                            )}

                            <section className="workforce-modal-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">emergency</span>
                                    <div>
                                        <h3>Emergency Contact & Notes</h3>
                                        <p>Optional information for workforce administration and work planning.</p>
                                    </div>
                                </div>
                                <div className="workforce-modal-form-grid">
                                    <div className="workforce-field">
                                        <label htmlFor="employee-emergency-name">Emergency Contact Person</label>
                                        <input id="employee-emergency-name" value={employeeForm.emergency_contact_name} onChange={(e)=>setEmployeeForm({...employeeForm,emergency_contact_name:e.target.value})}/>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="employee-emergency-relationship">Relationship</label>
                                        <input id="employee-emergency-relationship" placeholder="e.g. Spouse, Parent, Sibling" value={employeeForm.emergency_contact_relationship} onChange={(e)=>setEmployeeForm({...employeeForm,emergency_contact_relationship:e.target.value})}/>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="employee-emergency-number">Emergency Contact Number</label>
                                        <input id="employee-emergency-number" placeholder="e.g. 09XXXXXXXXX" value={employeeForm.emergency_contact_number} onChange={(e)=>setEmployeeForm({...employeeForm,emergency_contact_number:e.target.value})}/>
                                    </div>
                                    <div className="workforce-field full">
                                        <label htmlFor="employee-notes">Notes</label>
                                        <textarea id="employee-notes" placeholder="Optional notes about availability, work restrictions, or other assignment information" value={employeeForm.notes} onChange={(e)=>setEmployeeForm({...employeeForm,notes:e.target.value})}/>
                                    </div>
                                </div>
                            </section>

                            <section className="workforce-modal-section employee-login-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">passkey</span>
                                    <div>
                                        <h3>Login Access</h3>
                                        <p>The employee profile stays separate from authentication, but this creates or manages the linked System User account used to open My Tasks.</p>
                                    </div>
                                </div>

                                {employeeForm.has_login_account ? (
                                    <>
                                        <div className="employee-login-status-banner">
                                            <span className="material-symbols-outlined">verified_user</span>
                                            <div>
                                                <strong>Login account linked</strong>
                                                <span>Role: Employee · Account status: {employeeForm.login_status || "Active"}</span>
                                            </div>
                                        </div>
                                        <div className="workforce-modal-form-grid">
                                            <div className="workforce-field">
                                                <label htmlFor="employee-login-username">Username <span className="required-mark">*</span></label>
                                                <input id="employee-login-username" required minLength={3} maxLength={50} autoComplete="off" value={employeeForm.login_username} onChange={(e)=>setEmployeeForm({...employeeForm,login_username:e.target.value.toLowerCase().replace(/\s+/g, ".")})}/>
                                            </div>
                                            <div className="workforce-field">
                                                <label>System Role</label>
                                                <input value="Employee" disabled readOnly/>
                                            </div>
                                            <div className="workforce-field">
                                                <label htmlFor="employee-login-password">New Password <span className="field-optional">Optional</span></label>
                                                <input id="employee-login-password" type="password" minLength={8} autoComplete="new-password" placeholder="Leave blank to keep current password" value={employeeForm.login_password} onChange={(e)=>setEmployeeForm({...employeeForm,login_password:e.target.value})}/>
                                            </div>
                                            <div className="workforce-field">
                                                <label htmlFor="employee-login-password-confirm">Confirm New Password</label>
                                                <input id="employee-login-password-confirm" type="password" minLength={8} autoComplete="new-password" placeholder="Repeat the new password" value={employeeForm.login_password_confirm} onChange={(e)=>setEmployeeForm({...employeeForm,login_password_confirm:e.target.value})}/>
                                            </div>
                                            <div className="workforce-login-help full">
                                                <span className="material-symbols-outlined">security</span>
                                                Passwords are hashed by the backend and cannot be viewed later. Enter a new password only when resetting this employee's login.
                                            </div>
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <label className="employee-login-toggle">
                                            <input type="checkbox" checked={employeeForm.create_login_account} onChange={(e)=>setEmployeeForm((current)=>({
                                                ...current,
                                                create_login_account:e.target.checked,
                                                login_username:e.target.checked && !current.login_username ? suggestEmployeeUsername(current.full_name) : current.login_username,
                                                login_password:e.target.checked ? current.login_password : "",
                                                login_password_confirm:e.target.checked ? current.login_password_confirm : "",
                                            }))}/>
                                            <span className="material-symbols-outlined">person_check</span>
                                            <span>
                                                <strong>Create login account for this employee</strong>
                                                <small>Required if the employee will personally open My Tasks. Turn this off for workers whose tasks will be recorded through Assisted Submission.</small>
                                            </span>
                                        </label>

                                        {employeeForm.create_login_account && (
                                            <div className="workforce-modal-form-grid employee-login-fields">
                                                <div className="workforce-field">
                                                    <label htmlFor="employee-login-username">Username <span className="required-mark">*</span></label>
                                                    <input id="employee-login-username" required minLength={3} maxLength={50} autoComplete="off" placeholder="e.g. john.dela.cruz" value={employeeForm.login_username} onChange={(e)=>setEmployeeForm({...employeeForm,login_username:e.target.value.toLowerCase().replace(/\s+/g, ".")})}/>
                                                </div>
                                                <div className="workforce-field">
                                                    <label>System Role</label>
                                                    <input value="Employee" disabled readOnly/>
                                                </div>
                                                <div className="workforce-field">
                                                    <label htmlFor="employee-login-password">Initial Password <span className="required-mark">*</span></label>
                                                    <input id="employee-login-password" required type="password" minLength={8} autoComplete="new-password" placeholder="At least 8 characters" value={employeeForm.login_password} onChange={(e)=>setEmployeeForm({...employeeForm,login_password:e.target.value})}/>
                                                </div>
                                                <div className="workforce-field">
                                                    <label htmlFor="employee-login-password-confirm">Confirm Password <span className="required-mark">*</span></label>
                                                    <input id="employee-login-password-confirm" required type="password" minLength={8} autoComplete="new-password" placeholder="Repeat the password" value={employeeForm.login_password_confirm} onChange={(e)=>setEmployeeForm({...employeeForm,login_password_confirm:e.target.value})}/>
                                                </div>
                                                <div className="workforce-login-help full">
                                                    <span className="material-symbols-outlined">lock</span>
                                                    This creates a normal System User account with the fixed Employee role and links it to this employee profile.
                                                </div>
                                            </div>
                                        )}
                                    </>
                                )}
                            </section>

                            <footer className="workforce-modal-footer">
                                <div className="employee-position-limit-note">
                                    <span className="material-symbols-outlined">info</span>
                                    One employee can hold up to 5 active farm positions.
                                </div>
                                <div className="workforce-modal-footer-actions">
                                    <button type="button" className="workforce-modal-cancel" onClick={closeEmployeeModal}>Cancel</button>
                                    <button type="submit" className="workforce-modal-save">
                                        <span className="material-symbols-outlined" aria-hidden="true">{editingEmployeeId ? "save" : "person_add"}</span>
                                        {editingEmployeeId ? "Save Changes" : "Save Employee"}
                                    </button>
                                </div>
                            </footer>
                        </form>
                    </div>
                </div>
            )}

            {viewEmployee && (
                <div
                    className="workforce-modal-overlay"
                    onMouseDown={(event) => {
                        if (event.target === event.currentTarget) closeViewEmployeeModal();
                    }}
                >
                    <div
                        className="workforce-task-modal workforce-employee-view-modal"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="view-employee-modal-title"
                        onMouseDown={(event) => event.stopPropagation()}
                    >
                        <header className="workforce-modal-header">
                            <div>
                                <h2 id="view-employee-modal-title">Employee Profile</h2>
                                <p>View employee information, farm positions, current work assignments, and active tasks.</p>
                            </div>
                            <button type="button" className="workforce-modal-close" onClick={closeViewEmployeeModal} aria-label="Close employee profile">
                                <span className="material-symbols-outlined">close</span>
                            </button>
                        </header>

                        <div className="workforce-modal-form employee-view-body">
                            <section className="employee-view-identity">
                                <div className="employee-view-avatar">{(viewEmployee.full_name || "E").trim().charAt(0).toUpperCase()}</div>
                                <div className="employee-view-identity-copy">
                                    <span className="employee-view-code">{viewEmployee.employee_code}</span>
                                    <h3>{viewEmployee.full_name}</h3>
                                    <div className="employee-position-chips">
                                        {(viewEmployee.positions || []).length ? viewEmployee.positions.map((position) => (
                                            <span key={position.id} className={`employee-position-chip ${position.is_primary ? "primary" : ""}`}>
                                                {position.name}{position.is_primary ? " • Primary" : ""}
                                            </span>
                                        )) : <span className="employee-position-chip">{viewEmployee.position || "Employee"}</span>}
                                    </div>
                                </div>
                                <span className={`employee-status employee-view-status ${statusClass(viewEmployee.employment_status)}`}>{viewEmployee.employment_status}</span>
                            </section>

                            <section className="workforce-modal-section employee-view-details-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">badge</span>
                                    <div><h3>Employee Information</h3><p>Contact, employment, and workforce details saved in this employee profile.</p></div>
                                </div>
                                <div className="employee-view-detail-grid">
                                    <div><span>Contact Number</span><strong>{viewEmployee.contact_number || "—"}</strong></div>
                                    <div><span>Email</span><strong>{viewEmployee.email || "—"}</strong></div>
                                    <div><span>Employment Type</span><strong>{viewEmployee.employment_type || "—"}</strong></div>
                                    <div><span>Date Hired</span><strong>{viewEmployee.date_hired || "—"}</strong></div>
                                    <div><span>Usual Farm Area</span><strong>{viewEmployee.assigned_area || "—"}</strong></div>
                                    <div><span>Login Account</span><strong>{viewEmployee.account_status || "No Login Account"}{viewEmployee.login_username ? ` · ${viewEmployee.login_username}` : ""}</strong>{viewEmployee.account_issue && <small>{viewEmployee.account_issue}</small>}</div>
                                    <div className="wide"><span>Address</span><strong>{viewEmployee.address || "—"}</strong></div>
                                    <div className="wide"><span>Skills / Specializations</span><strong>{viewEmployee.skills || "—"}</strong></div>
                                </div>
                            </section>

                            <section className="workforce-modal-section employee-view-assignments-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">location_on</span>
                                    <div><h3>Current Farm Assignments</h3><p>These are the active crop fields and livestock records currently assigned to this employee.</p></div>
                                </div>
                                {viewEmployeeLoading ? (
                                    <div className="workforce-inline-loading">Loading current assignments…</div>
                                ) : (
                                    <div className="employee-view-assignment-grid">
                                        <div className="employee-view-assignment-group">
                                            <div className="employee-view-assignment-group-title"><span className="material-symbols-outlined">psychiatry</span><strong>Crop / Field</strong><span>{viewEmployeeAssignments.crops.length}</span></div>
                                            <div className="employee-view-assignment-items">
                                                {viewEmployeeAssignments.crops.length ? viewEmployeeAssignments.crops.map((item) => (
                                                    <div key={`view-crop-${item.id}`} className="employee-view-assignment-item">
                                                        <strong>{item.name}</strong>
                                                        <span>{item.record_code} • {item.location || "No field"}</span>
                                                        {item.detail && <small>{item.detail}</small>}
                                                    </div>
                                                )) : <div className="employee-view-assignment-empty">No crop or field assignment.</div>}
                                            </div>
                                        </div>
                                        <div className="employee-view-assignment-group">
                                            <div className="employee-view-assignment-group-title"><span className="material-symbols-outlined">pets</span><strong>Livestock / Pen</strong><span>{viewEmployeeAssignments.livestock.length}</span></div>
                                            <div className="employee-view-assignment-items">
                                                {viewEmployeeAssignments.livestock.length ? viewEmployeeAssignments.livestock.map((item) => (
                                                    <div key={`view-livestock-${item.id}`} className="employee-view-assignment-item">
                                                        <strong>{item.name}</strong>
                                                        <span>{item.record_code} • {item.location || "No pen"}</span>
                                                        {item.detail && <small>{item.detail}</small>}
                                                    </div>
                                                )) : <div className="employee-view-assignment-empty">No livestock or pen assignment.</div>}
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </section>

                            <section className="workforce-modal-section employee-view-tasks-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">assignment</span>
                                    <div><h3>Active Tasks</h3><p>Open work currently assigned to this employee. Individual task ownership is changed from the Tasks tab using Reassign.</p></div>
                                </div>
                                {viewEmployeeLoading ? (
                                    <div className="workforce-inline-loading">Loading active tasks…</div>
                                ) : viewEmployeeTasks.length ? (
                                    <div className="employee-view-task-list">
                                        {viewEmployeeTasks.map((task) => (
                                            <div key={`employee-task-${task.id}`} className="employee-view-task-row">
                                                <div><strong>{task.name}</strong><span>{task.related_to}{task.location ? ` • ${task.location}` : ""}</span></div>
                                                <div className="employee-view-task-date"><span>{task.activity_date}</span><small>{task.start_time || ""}</small></div>
                                                <span className={`task-status ${statusClass(task.status)}`}>{task.status}</span>
                                            </div>
                                        ))}
                                    </div>
                                ) : <div className="employee-view-assignment-empty">No active tasks are currently assigned to this employee.</div>}
                            </section>

                            {(viewEmployee.emergency_contact_name || viewEmployee.notes) && (
                                <section className="workforce-modal-section employee-view-details-section">
                                    <div className="workforce-modal-section-title">
                                        <span className="material-symbols-outlined">emergency</span>
                                        <div><h3>Emergency Contact & Notes</h3><p>Additional workforce information.</p></div>
                                    </div>
                                    <div className="employee-view-detail-grid">
                                        <div><span>Emergency Contact</span><strong>{viewEmployee.emergency_contact_name || "—"}</strong></div>
                                        <div><span>Relationship</span><strong>{viewEmployee.emergency_contact_relationship || "—"}</strong></div>
                                        <div><span>Contact Number</span><strong>{viewEmployee.emergency_contact_number || "—"}</strong></div>
                                        <div className="wide"><span>Notes</span><strong>{viewEmployee.notes || "—"}</strong></div>
                                    </div>
                                </section>
                            )}
                        </div>

                        <footer className="workforce-modal-footer employee-view-footer">
                            <button type="button" className="workforce-modal-cancel" onClick={closeViewEmployeeModal}>Close</button>
                            <button type="button" className="workforce-modal-save" onClick={() => { const employee = viewEmployee; closeViewEmployeeModal(); openEditEmployee(employee); }}>
                                <span className="material-symbols-outlined">edit</span>
                                Edit Employee
                            </button>
                        </footer>
                    </div>
                </div>
            )}

            {reassignTask && (
                <div
                    className="workforce-modal-overlay"
                    onMouseDown={(event) => {
                        if (event.target === event.currentTarget) closeReassignModal();
                    }}
                >
                    <div
                        className="workforce-task-modal workforce-reassign-modal"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="reassign-task-modal-title"
                        onMouseDown={(event) => event.stopPropagation()}
                    >
                        <header className="workforce-modal-header">
                            <div>
                                <h2 id="reassign-task-modal-title">Reassign Task</h2>
                                <p>Select an active employee whose primary or additional farm positions fit this work.</p>
                            </div>
                            <button type="button" className="workforce-modal-close" onClick={closeReassignModal} aria-label="Close reassign task modal">
                                <span className="material-symbols-outlined">close</span>
                            </button>
                        </header>

                        <div className="workforce-modal-form reassign-modal-body">
                            <section className="workforce-modal-section reassign-task-summary">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">assignment</span>
                                    <div>
                                        <h3>{reassignTask.name}</h3>
                                        <p>{reassignTask.activity_code} · {reassignTask.related_to || "General Farm"} · {reassignTask.activity_date} {reassignTask.start_time || ""}</p>
                                    </div>
                                </div>
                                <div className="reassign-task-facts">
                                    <div><span>Category</span><strong>{reassignTask.category || "General"}</strong></div>
                                    <div><span>Location</span><strong>{reassignTask.location || "Jorros Farm"}</strong></div>
                                    <div><span>Current Employee</span><strong>{reassignTask.employee_name || "Unassigned"}</strong></div>
                                    <div><span>Detected Work Type</span><strong>{reassignProfile.activities[0]?.label || reassignProfile.domain?.label || "General Farm Work"}</strong></div>
                                </div>
                                <div className="reassign-role-hints">
                                    <span className="reassign-role-label">Suggested positions</span>
                                    <div className="reassign-role-chips">
                                        {reassignProfile.suggestedRoles.map((role) => <span key={role}>{role}</span>)}
                                    </div>
                                    <p>Both <strong>primary and additional positions</strong> are considered. Primary matches rank slightly higher, but a matching secondary role is still recommended.</p>
                                </div>
                            </section>

                            <section className="workforce-modal-section reassign-employee-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">person_search</span>
                                    <div>
                                        <h3>Choose Employee</h3>
                                        <p>Recommended employees are ranked from the farm positions saved in their employee profile.</p>
                                    </div>
                                </div>

                                <div className="reassign-search">
                                    <span className="material-symbols-outlined">search</span>
                                    <input
                                        type="search"
                                        placeholder="Search employee, code, position, or farm area…"
                                        value={reassignSearch}
                                        onChange={(event) => setReassignSearch(event.target.value)}
                                        autoFocus
                                    />
                                </div>

                                {!reassignCandidates.length ? (
                                    <div className="reassign-empty">
                                        <span className="material-symbols-outlined">person_off</span>
                                        <div>
                                            <strong>No available employee found</strong>
                                            <p>There are no active employees matching this search. Activate or add an employee first.</p>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="reassign-candidate-groups">
                                        {!!recommendedReassignCandidates.length && (
                                            <div className="reassign-candidate-group">
                                                <div className="reassign-group-title">
                                                    <span className="material-symbols-outlined">recommend</span>
                                                    Recommended Employees
                                                    <span className="reassign-count">{recommendedReassignCandidates.length}</span>
                                                </div>
                                                <div className="reassign-candidate-list">
                                                    {recommendedReassignCandidates.map((candidate) => {
                                                        const selected = String(reassignEmployeeId) === String(candidate.employee.id);
                                                        return (
                                                            <button
                                                                type="button"
                                                                key={candidate.employee.id}
                                                                className={`reassign-candidate ${selected ? "selected" : ""}`}
                                                                onClick={() => setReassignEmployeeId(String(candidate.employee.id))}
                                                                disabled={!candidate.employee.portal_assignment_ready}
                                                            >
                                                                <span className={`reassign-radio ${selected ? "selected" : ""}`}>{selected && <span/>}</span>
                                                                <span className="reassign-candidate-main">
                                                                    <span className="reassign-candidate-top">
                                                                        <span>
                                                                            <strong>{candidate.employee.full_name}</strong>
                                                                            <small>{candidate.employee.employee_code}{candidate.employee.assigned_area ? ` · ${candidate.employee.assigned_area}` : ""} · {candidate.employee.account_status || "No Login Account"}</small>
                                                                        </span>
                                                                        <span className="reassign-recommended-badge">Recommended</span>
                                                                    </span>
                                                                    <span className="reassign-position-list">
                                                                        {(candidate.employee.positions || []).map((position) => {
                                                                            const matched = candidate.matchedPositions.some((item) => item.id === position.id);
                                                                            return (
                                                                                <span key={position.id} className={`reassign-position-chip ${matched ? "matched" : ""}`}>
                                                                                    {position.name}
                                                                                    <small>{position.is_primary ? "Primary" : "Additional"}</small>
                                                                                </span>
                                                                            );
                                                                        })}
                                                                    </span>
                                                                    <span className="reassign-match-note">
                                                                        <span className="material-symbols-outlined">verified</span>
                                                                        {candidate.hasPrimaryMatch && candidate.hasSecondaryMatch
                                                                            ? "Matches both primary and additional positions"
                                                                            : candidate.hasPrimaryMatch
                                                                                ? `Primary position match${candidate.matchedReasons.length ? ` · ${candidate.matchedReasons.join(" / ")}` : ""}`
                                                                                : `Additional position match${candidate.matchedReasons.length ? ` · ${candidate.matchedReasons.join(" / ")}` : ""}`}
                                                                    </span>
                                                                </span>
                                                            </button>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        )}

                                        {!!otherReassignCandidates.length && (
                                            <div className="reassign-candidate-group">
                                                <div className="reassign-group-title secondary-group-title">
                                                    <span className="material-symbols-outlined">group</span>
                                                    Other Active Employees
                                                    <span className="reassign-count">{otherReassignCandidates.length}</span>
                                                </div>
                                                {!recommendedReassignCandidates.length && (
                                                    <div className="reassign-no-exact-match">No exact farm-position match was found. You can still choose another active employee if the manager considers them suitable.</div>
                                                )}
                                                <div className="reassign-candidate-list">
                                                    {otherReassignCandidates.map((candidate) => {
                                                        const selected = String(reassignEmployeeId) === String(candidate.employee.id);
                                                        return (
                                                            <button
                                                                type="button"
                                                                key={candidate.employee.id}
                                                                className={`reassign-candidate ${selected ? "selected" : ""}`}
                                                                onClick={() => setReassignEmployeeId(String(candidate.employee.id))}
                                                                disabled={!candidate.employee.portal_assignment_ready}
                                                            >
                                                                <span className={`reassign-radio ${selected ? "selected" : ""}`}>{selected && <span/>}</span>
                                                                <span className="reassign-candidate-main">
                                                                    <span className="reassign-candidate-top">
                                                                        <span>
                                                                            <strong>{candidate.employee.full_name}</strong>
                                                                            <small>{candidate.employee.employee_code}{candidate.employee.assigned_area ? ` · ${candidate.employee.assigned_area}` : ""} · {candidate.employee.account_status || "No Login Account"}</small>
                                                                        </span>
                                                                    </span>
                                                                    <span className="reassign-position-list">
                                                                        {(candidate.employee.positions || []).map((position) => (
                                                                            <span key={position.id} className="reassign-position-chip">
                                                                                {position.name}
                                                                                <small>{position.is_primary ? "Primary" : "Additional"}</small>
                                                                            </span>
                                                                        ))}
                                                                    </span>
                                                                    <span className="reassign-match-note muted">No direct position match detected</span>
                                                                </span>
                                                            </button>
                                                        );
                                                    })}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </section>

                            <footer className="workforce-modal-footer">
                                <button type="button" className="workforce-modal-cancel" onClick={closeReassignModal} disabled={reassignSaving}>Cancel</button>
                                <button type="button" className="workforce-modal-save" onClick={performTaskReassignment} disabled={!reassignEmployeeId || reassignSaving}>
                                    <span className="material-symbols-outlined">assignment_ind</span>
                                    {reassignSaving ? "Reassigning…" : "Reassign Task"}
                                </button>
                            </footer>
                        </div>
                    </div>
                </div>
            )}

            {assistedTask && (
                <div className="workforce-modal-overlay" onMouseDown={(event)=>{ if (event.target === event.currentTarget) closeAssistedModal(); }}>
                    <div className="workforce-task-modal assisted-submission-modal" role="dialog" aria-modal="true" aria-labelledby="assisted-submission-title" onMouseDown={(event)=>event.stopPropagation()}>
                        <header className="workforce-modal-header">
                            <div>
                                <h2 id="assisted-submission-title">{assistedCorrectionMode ? "Correct Resource Usage" : "Record Work for Employee"}</h2>
                                <p>{assistedCorrectionMode ? "Correct the recorded actual quantity while preserving the completed task and its audit history." : "Use this when the employee performed the task but could not or forgot to submit it from My Tasks."}</p>
                            </div>
                            <button type="button" className="workforce-modal-close" onClick={closeAssistedModal} aria-label="Close assisted submission modal">
                                <span className="material-symbols-outlined">close</span>
                            </button>
                        </header>

                        <div className="workforce-modal-form">
                            <section className="workforce-modal-section assisted-task-summary">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">assignment</span>
                                    <div><h3>{assistedTask.name}</h3><p>{assistedTask.related_to} · {assistedTask.location} · {assistedTask.activity_date}</p></div>
                                </div>
                                <div className="assisted-audit-note">
                                    <span className="material-symbols-outlined">history</span>
                                    <span>The employee remains the performer. Your Admin/Manager account is saved separately as the recorder.</span>
                                </div>
                            </section>

                            <section className="workforce-modal-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">badge</span>
                                    <div><h3>Performed Work</h3><p>Record who actually performed the task and what was actually used or completed.</p></div>
                                </div>
                                <div className="workforce-modal-form-grid">
                                    <div className="workforce-field">
                                        <label htmlFor="assisted-performer">Performed By *</label>
                                        <select id="assisted-performer" value={assistedForm.employee_id} onChange={(event)=>setAssistedForm({...assistedForm, employee_id:event.target.value})}>
                                            <option value="">Select employee</option>
                                            {assistedEmployeeOptions.map((employee)=><option key={employee.id} value={employee.id}>{employee.full_name} — {employeePositionLabel(employee)}{employee.employment_status !== "Active" || employee.is_archived ? ` (${employee.is_archived ? "Archived" : employee.employment_status})` : ""}</option>)}
                                        </select>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="assisted-reason">Reason for Assisted Entry *</label>
                                        <select id="assisted-reason" value={assistedForm.assisted_reason} onChange={(event)=>setAssistedForm({...assistedForm, assisted_reason:event.target.value})}>
                                            {assistedCorrectionMode ? (
                                                <>
                                                    <option>Correct actual resource quantity</option>
                                                    <option>Correct wrong inventory item</option>
                                                    <option>Correct unit/usage entry</option>
                                                    <option>Manager verified a recording error</option>
                                                </>
                                            ) : (
                                                <>
                                                    <option>Employee forgot to submit</option>
                                                    <option>Employee had no device access</option>
                                                    <option>Network / connectivity problem</option>
                                                    <option>Manager observed the completed work</option>
                                                    <option>Shared-device entry by manager</option>
                                                </>
                                            )}
                                        </select>
                                    </div>
                                    {assistedIsCropHarvest && (
                                        <>
                                            <div className="workforce-field">
                                                <label htmlFor="assisted-harvest-quantity">Actual Harvest Yield (kg) *</label>
                                                <input
                                                    id="assisted-harvest-quantity"
                                                    type="number"
                                                    min="0.001"
                                                    step="0.001"
                                                    required
                                                    placeholder="Enter the actual harvested weight"
                                                    value={assistedForm.actual_quantity}
                                                    onChange={(event)=>setAssistedForm({...assistedForm, actual_quantity:event.target.value, actual_quantity_confirmed:false})}
                                                />
                                                <small className="workforce-field-help">Enter only the kilograms harvested during this task occurrence.</small>
                                            </div>
                                            <div className="workforce-field">
                                                <label htmlFor="assisted-harvest-type">Reported Harvest Type *</label>
                                                <select
                                                    id="assisted-harvest-type"
                                                    required
                                                    value={assistedForm.harvest_type_intent}
                                                    onChange={(event)=>setAssistedForm({...assistedForm, harvest_type_intent:event.target.value})}
                                                >
                                                    <option value="">Select harvest type</option>
                                                    <option value="Partial Harvest">Partial Harvest</option>
                                                    <option value="Final Harvest">Final/Fully Harvested</option>
                                                </select>
                                                <small className="workforce-field-help">The reviewer must confirm this same choice before the crop lifecycle changes.</small>
                                            </div>
                                            <div className="workforce-field full">
                                                <label className="workforce-checkbox-row">
                                                    <input
                                                        type="checkbox"
                                                        checked={Boolean(assistedForm.actual_quantity_confirmed)}
                                                        onChange={(event)=>setAssistedForm({...assistedForm, actual_quantity_confirmed:event.target.checked})}
                                                    />
                                                    <span>I confirm the entered kg is the employee's actual harvested yield.</span>
                                                </label>
                                                <small className="workforce-field-help">Required for a late manager-recorded harvest entry. Do not use an estimated or planned value.</small>
                                            </div>
                                            <div className="assisted-harvest-review-note full" role="note">
                                                <span className="material-symbols-outlined" aria-hidden="true">fact_check</span>
                                                <span>This harvest can only be submitted for review. A manager must review the evidence and confirm Partial or Final Harvest before any crop lifecycle change.</span>
                                            </div>
                                        </>
                                    )}
                                    {assistedTask.resource_required && (
                                        <>
                                            {!assistedTask.resource_linked && (
                                                <div className="workforce-field full">
                                                    <label htmlFor="assisted-inventory-resource">Inventory Resource *</label>
                                                    <select id="assisted-inventory-resource" required value={assistedForm.inventory_item_id} onChange={(event)=>{
                                                        const item = inventoryItems.find((entry)=>String(entry.id) === String(event.target.value));
                                                        setAssistedForm({...assistedForm, inventory_item_id:event.target.value, actual_unit:item?.unit || "", actual_quantity_confirmed:false});
                                                    }}>
                                                        <option value="">Select the exact inventory item used</option>
                                                        {assistedResourceItems.map((item)=><option key={item.id} value={item.id}>{item.itemCode} — {item.name} · {item.quantity} {item.unit} available</option>)}
                                                    </select>
                                                    <small className="workforce-field-help">This task needs a tracked resource but none was linked when it was generated. Selecting one here links it to the task for future corrections and reporting.</small>
                                                </div>
                                            )}
                                            <div className="workforce-resource-summary full">
                                                <div className="workforce-resource-summary-icon"><span className="material-symbols-outlined">inventory_2</span></div>
                                                <div className="workforce-resource-summary-copy">
                                                    <span>Inventory Resource</span>
                                                    <strong>{assistedTask.resource_linked ? (assistedTask.planned_inventory_item_name || "Linked inventory item") : (assistedSelectedInventoryItem?.name || "Select an inventory item above")}</strong>
                                                    <small>{assistedTask.resource_linked ? `${assistedTask.planned_inventory_item_code || ""}${assistedTask.planned_inventory_category ? ` · ${assistedTask.planned_inventory_category}` : ""}` : assistedSelectedInventoryItem ? `${assistedSelectedInventoryItem.itemCode} · ${assistedSelectedInventoryItem.category}` : "No inventory item linked yet"}</small>
                                                </div>
                                                <div className="workforce-resource-metrics">
                                                    <div><span>Planned</span><strong>{assistedTask.planned_quantity != null ? `${assistedTask.planned_quantity} ${assistedTask.resource_linked ? (assistedTask.planned_inventory_unit || assistedTask.planned_unit || "") : (assistedSelectedInventoryItem?.unit || assistedTask.planned_unit || "")}` : "Not set"}</strong></div>
                                                    <div><span>Available Before Use</span><strong>{assistedTask.resource_linked && assistedTask.planned_inventory_available_quantity != null ? `${assistedTask.planned_inventory_available_quantity} ${assistedTask.planned_inventory_unit || ""}` : assistedSelectedInventoryItem ? `${assistedSelectedInventoryItem.quantity} ${assistedSelectedInventoryItem.unit}` : "—"}</strong></div>
                                                </div>
                                            </div>
                                            <div className="workforce-field">
                                                <label htmlFor="assisted-actual-quantity">Actual Quantity Used *</label>
                                                <input id="assisted-actual-quantity" type="number" min="0" step="0.001" required placeholder={assistedTask.planned_quantity != null ? `Planned: ${assistedTask.planned_quantity}` : "Enter actual usage"} value={assistedForm.actual_quantity} onChange={(event)=>setAssistedForm({...assistedForm, actual_quantity:event.target.value, actual_quantity_confirmed:false})}/>
                                                <small className="workforce-field-help">Submit for Review reserves this actual quantity. Inventory is deducted only when Admin/Manager approves it. Submit &amp; Approve deducts immediately because the manager is approving the work in the same action.</small>
                                            </div>
                                            <div className="workforce-field">
                                                <label htmlFor="assisted-unit">Inventory Unit</label>
                                                <input id="assisted-unit" value={assistedTask.resource_linked ? assistedForm.actual_unit : (assistedSelectedInventoryItem?.unit || assistedForm.actual_unit)} readOnly/>
                                            </div>
                                            <div className="workforce-field full">
                                                <label className="workforce-checkbox-row">
                                                    <input
                                                        type="checkbox"
                                                        checked={Boolean(assistedForm.actual_quantity_confirmed)}
                                                        onChange={(event)=>setAssistedForm({...assistedForm, actual_quantity_confirmed:event.target.checked})}
                                                    />
                                                    <span>I confirm the quantity above is the actual amount used, not only the planned amount.</span>
                                                </label>
                                                <small className="workforce-field-help">Required for a late manager-recorded entry. Verify the employee's actual kg or other inventory unit before submitting or approving.</small>
                                            </div>
                                            <div className="workforce-field full">
                                                <label className="workforce-checkbox-row">
                                                    <input
                                                        type="checkbox"
                                                        checked={Boolean(assistedForm.allow_negative_inventory)}
                                                        onChange={(event)=>setAssistedForm({
                                                            ...assistedForm,
                                                            allow_negative_inventory: event.target.checked,
                                                            inventory_override_reason: event.target.checked ? assistedForm.inventory_override_reason : "",
                                                        })}
                                                    />
                                                    <span>Authorized negative-stock override</span>
                                                </label>
                                                <small className="workforce-field-help">Use only when the physical resource was already consumed and a manager has verified the inventory discrepancy. The override is applied only when the work is approved.</small>
                                            </div>
                                            {assistedForm.allow_negative_inventory && (
                                                <div className="workforce-field full">
                                                    <label htmlFor="assisted-inventory-override-reason">Override Reason *</label>
                                                    <textarea
                                                        id="assisted-inventory-override-reason"
                                                        required
                                                        placeholder="Explain why negative stock is authorized and how the discrepancy will be reconciled."
                                                        value={assistedForm.inventory_override_reason}
                                                        onChange={(event)=>setAssistedForm({...assistedForm, inventory_override_reason:event.target.value})}
                                                    />
                                                </div>
                                            )}
                                        </>
                                    )}
                                    <MonitoringObservationFields context={assistedTask.monitoring_context} value={assistedForm.monitoring} onChange={(monitoring) => setAssistedForm({ ...assistedForm, monitoring })} disabled={assistedSaving} />
                                    <EvidencePhotoField
                                        taskId={assistedTask.id}
                                        value={assistedForm.evidence_url}
                                        onChange={(value)=>setAssistedForm({...assistedForm,evidence_url:value})}
                                        required={assistedTask.requires_evidence}
                                        disabled={assistedSaving}
                                        label="Evidence Photo"
                                        helpText="Upload or take a photo of the work recorded for this employee."
                                    />
                                    <div className="workforce-field full">
                                        <label htmlFor="assisted-notes">Work Notes</label>
                                        <textarea id="assisted-notes" placeholder="What work was performed? Include useful details for the review history." value={assistedForm.worker_notes} onChange={(event)=>setAssistedForm({...assistedForm, worker_notes:event.target.value})}/>
                                    </div>
                                </div>
                            </section>
                        </div>

                        <footer className="workforce-modal-footer">
                            <button type="button" className="workforce-modal-cancel" onClick={closeAssistedModal} disabled={assistedSaving}>Cancel</button>
                            {!assistedCorrectionMode && (
                                <button type="button" className="workforce-modal-review-submit" onClick={()=>submitAssistedWork(false)} disabled={assistedSaving}>
                                    <span className="material-symbols-outlined">rate_review</span>
                                    {assistedIsCropHarvest ? "Submit Harvest for Review" : "Submit for Review"}
                                </button>
                            )}
                            {!assistedIsCropHarvest && (
                                <button type="button" className="workforce-modal-save" onClick={()=>submitAssistedWork(true)} disabled={assistedSaving || Boolean(assistedTask.monitoring_context)}>
                                    <span className="material-symbols-outlined">task_alt</span>
                                    {assistedSaving ? "Saving…" : assistedCorrectionMode ? "Save Usage Correction" : "Submit & Approve"}
                                </button>
                            )}
                        </footer>
                    </div>
                </div>
            )}

            {employeeAction && (
                <div className="workforce-modal-overlay" onMouseDown={(event)=>{ if (event.target === event.currentTarget) closeEmployeeActionModal(); }}>
                    <div className="workforce-confirm-modal" role="dialog" aria-modal="true" onMouseDown={(event)=>event.stopPropagation()}>
                        <header className="workforce-modal-header">
                            <div>
                                <h2>
                                    {employeeAction.type === "archive" ? "Archive Employee" : employeeAction.type === "restore" ? "Restore Employee" : employeeAction.nextStatus === "Active" ? "Activate Employee" : "Deactivate Employee"}
                                </h2>
                                <p>Manage the employee lifecycle while preserving workforce and farm history.</p>
                            </div>
                            <button type="button" className="workforce-modal-close" onClick={closeEmployeeActionModal} aria-label="Close confirmation">
                                <span className="material-symbols-outlined">close</span>
                            </button>
                        </header>
                        <div className="workforce-confirm-body">
                            <div className={`workforce-confirm-icon ${employeeAction.type}`}>
                                <span className="material-symbols-outlined">{employeeAction.type === "archive" ? "archive" : employeeAction.type === "restore" ? "unarchive" : employeeAction.nextStatus === "Active" ? "person_check" : "person_off"}</span>
                            </div>
                            <div className="workforce-confirm-copy">
                                <h3>{employeeAction.employee.full_name}</h3>
                                {employeeAction.type === "archive" && (
                                    <>
                                        <p>This profile will move to the Archives tab. Historical tasks, attendance, positions, and resource records will remain available. Current Crop/Field and Livestock/Pen responsibility will be released so new work is not routed to the archived employee.</p>
                                        {tasks.filter((task)=>task.assigned_employee_id === employeeAction.employee.id && ["Pending","In Progress","Returned"].includes(task.status)).length > 0 && (
                                            <div className="workforce-action-warning">
                                                <span className="material-symbols-outlined">warning</span>
                                                This employee has {tasks.filter((task)=>task.assigned_employee_id === employeeAction.employee.id && ["Pending","In Progress","Returned"].includes(task.status)).length} unfinished task(s). They will be flagged for reassignment.
                                            </div>
                                        )}
                                        <div className="workforce-field archive-reason-field">
                                            <label htmlFor="archive-reason">Archive Reason <span>(optional)</span></label>
                                            <textarea id="archive-reason" value={archiveReason} onChange={(event)=>setArchiveReason(event.target.value)} placeholder="e.g. End of contract, resigned, no longer working at the farm"/>
                                        </div>
                                    </>
                                )}
                                {employeeAction.type === "status" && employeeAction.nextStatus === "Inactive" && (
                                    <p>Inactive employees stay in the Employees table and keep their history, but they cannot receive new assignments. Unfinished tasks will be flagged for reassignment.</p>
                                )}
                                {employeeAction.type === "status" && employeeAction.nextStatus === "Active" && (
                                    <p>This employee will become available for new task assignments again.</p>
                                )}
                                {employeeAction.type === "restore" && (
                                    <p>The employee will return to the Employees tab as <strong>Inactive</strong>. Activate the profile when the worker is ready to receive new assignments.</p>
                                )}
                            </div>
                        </div>
                        <footer className="workforce-confirm-footer">
                            <button type="button" className="workforce-modal-cancel" onClick={closeEmployeeActionModal}>Cancel</button>
                            <button type="button" className={`workforce-modal-save ${employeeAction.type === "archive" ? "danger-action" : ""}`} onClick={performEmployeeAction}>
                                <span className="material-symbols-outlined">{employeeAction.type === "archive" ? "archive" : employeeAction.type === "restore" ? "unarchive" : employeeAction.nextStatus === "Active" ? "person_check" : "person_off"}</span>
                                {employeeAction.type === "archive" ? "Archive Employee" : employeeAction.type === "restore" ? "Restore Employee" : employeeAction.nextStatus === "Active" ? "Activate Employee" : "Deactivate Employee"}
                            </button>
                        </footer>
                    </div>
                </div>
            )}

            {showTaskForm && (
                <div
                    className="workforce-modal-overlay"
                    onMouseDown={(event) => {
                        if (event.target === event.currentTarget) closeTaskModal();
                    }}
                >
                    <div
                        className="workforce-task-modal"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="assign-task-modal-title"
                        onMouseDown={(event) => event.stopPropagation()}
                    >
                        <header className="workforce-modal-header">
                            <div>
                                <h2 id="assign-task-modal-title">Assign Task</h2>
                                <p>Create a farm assignment, select an employee, and set the work schedule and review requirements.</p>
                            </div>
                            <button
                                type="button"
                                className="workforce-modal-close"
                                onClick={closeTaskModal}
                                aria-label="Close assign task form"
                            >
                                <span className="material-symbols-outlined">close</span>
                            </button>
                        </header>

                        <form className="workforce-modal-form" onSubmit={saveTask} aria-busy={taskSaving}>
                            {existingTaskId && <p role="status">This occurrence already has a task. <a href={`/task-management?taskId=${existingTaskId}`}>Open existing task</a></p>}
                            <fieldset disabled={taskSaving} style={{ border: 0, padding: 0, margin: 0, minWidth: 0, display: "grid", gap: "20px" }}>
                            <section className="workforce-modal-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">assignment</span>
                                    <div>
                                        <h3>Task Information</h3>
                                        <p>Enter the basic details of the work that needs to be completed.</p>
                                    </div>
                                </div>
                                <div className="workforce-modal-form-grid">
                                    <div className="workforce-field">
                                        <label htmlFor="assign-task-name">Task Name</label>
                                        <input id="assign-task-name" required value={taskForm.name} onChange={(e)=>setTaskForm({...taskForm,name:e.target.value})}/>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="assign-task-category">Category</label>
                                        <datalist id="task-work-categories">{WORK_TYPES.map((category) => <option key={category} value={category}>{workTypeLabel(category)}</option>)}</datalist>
                                        <input list="task-work-categories" id="assign-task-category" required value={taskForm.category} onChange={(e)=>setTaskForm(taskCategoryUpdate(taskForm, e.target.value))}/>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="assign-task-related">Related To</label>
                                        <input id="assign-task-related" value={taskForm.related_to} onChange={(e)=>setTaskForm({...taskForm,related_to:e.target.value})}/>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="assign-task-location">Location</label>
                                        <input id="assign-task-location" value={taskForm.location} onChange={(e)=>setTaskForm({...taskForm,location:e.target.value})}/>
                                    </div>
                                </div>
                            </section>

                            <section className="workforce-modal-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">inventory_2</span>
                                    <div>
                                        <h3>Farm Record & Resource</h3>
                                        <p>Link the task to its crop, livestock or restocking item. For work that consumes inventory, choose the same resource and planned amount used in Add Farm Event.</p>
                                    </div>
                                </div>
                                <div className="workforce-modal-form-grid">
                                    <div className="workforce-field">
                                        <label htmlFor="assign-task-source-module">Farm Record Type</label>
                                        <select
                                            id="assign-task-source-module"
                                            disabled={["Crop", "Livestock", "Inventory"].includes(eventDomain(taskForm.category))}
                                            value={taskForm.source_module}
                                            onChange={(event) => {
                                                const module = event.target.value;
                                                setTaskForm({
                                                    ...taskForm,
                                                    source_module: module,
                                                    source_type: module ? "manual_work" : "",
                                                    source_record_id: "",
                                                    planned_inventory_item_id: "",
                                                    planned_usage_type: "",
                                                    planned_quantity: "",
                                                    planned_unit: "",
                                                });
                                            }}
                                        >
                                            <option value="">General farm task</option>
                                            <option value="Crop">Crop / Field</option>
                                            <option value="Livestock">Livestock / Pen</option>
                                            {taskForm.category === "Inventory Restocking" && <option value="Inventory">Inventory / Storage</option>}
                                        </select>
                                    </div>
                                    {taskForm.source_module === "Inventory" && <p className="workforce-field-help">Restocking plans schedule a delivery. Record received stock in Inventory → Stock Adjustment; task approval does not change stock.</p>}
                                    <div className="workforce-field">
                                        <label htmlFor="assign-task-source-record">Related Farm Record</label>
                                        <select
                                            id="assign-task-source-record"
                                            disabled={!taskForm.source_module}
                                            required={Boolean(taskForm.source_module)}
                                            value={taskForm.source_record_id}
                                            onChange={(event) => {
                                                const recordId = event.target.value;
                                                const record = taskSourceOptions.find((entry) => String(entry.id) === String(recordId));
                                                const isCrop = taskForm.source_module === "Crop";
                                                setTaskForm({
                                                    ...taskForm,
                                                    source_record_id: recordId,
                                                    feeding_slot: "", planned_inventory_item_id: "", planned_quantity: "", planned_unit: "", planned_usage_type: "",
                                                    related_to: record
                                                        ? (isCrop ? `${record.name} — ${record.field}` : taskForm.source_module === "Inventory" ? record.name : record.recordName)
                                                        : taskForm.related_to,
                                                    location: record
                                                        ? (isCrop ? record.field : taskForm.source_module === "Inventory" ? record.location : (record.penLocation || "Jorros Farm"))
                                                        : taskForm.location,
                                                });
                                            }}
                                        >
                                            <option value="">{taskForm.source_module ? "Select record" : "Choose a record type first"}</option>
                                            {taskSourceOptions.map((record) => (
                                                <option key={record.id} value={record.id}>
                                                    {taskForm.source_module === "Crop"
                                                        ? `${record.cropCode || "Crop"} — ${record.name} · ${record.field}`
                                                        : taskForm.source_module === "Inventory" ? `${record.itemCode || "Inventory"} — ${record.name} · ${record.location || "No storage location"}`
                                                        : `${record.animalId || "Livestock"} — ${record.recordName} · ${record.penLocation || "No pen"}`}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="workforce-field full">
                                        <label htmlFor="assign-task-inventory-resource">Inventory Resource <span className="field-optional">(optional)</span></label>
                                        <select
                                            id="assign-task-inventory-resource"
                                            disabled={!["Crop", "Livestock"].includes(taskForm.source_module) || !taskForm.source_record_id || ["Weight Monitoring", "Crop Growth Monitoring"].includes(taskForm.category)}
                                            value={taskForm.planned_inventory_item_id}
                                            onChange={(event) => {
                                                const item = inventoryItems.find((entry) => String(entry.id) === String(event.target.value));
                                                setTaskForm({
                                                    ...taskForm,
                                                    planned_inventory_item_id: event.target.value,
                                                    planned_unit: item?.unit || "",
                                                    planned_usage_type: "",
                                                    planned_quantity: event.target.value ? taskForm.planned_quantity : "",
                                                });
                                            }}
                                        >
                                            <option value="">No inventory deduction for this task</option>
                                            {manualTaskResourceItems.map((item) => (
                                                <option key={item.id} value={item.id} disabled={Boolean(item.expirationDate && taskForm.activity_date > item.expirationDate)}>
                                                    {item.itemCode} — {item.name} · {item.quantity} {item.unit} available{item.expirationDate && taskForm.activity_date > item.expirationDate ? " — expires before work date" : ""}
                                                </option>
                                            ))}
                                        </select>
                                        {!taskForm.source_record_id && taskForm.source_module && (
                                            <small className="workforce-field-help">Select the specific crop or livestock record before linking inventory.</small>
                                        )}
                                        {selectedTaskInventoryItem && (
                                            <small className="workforce-field-help">Approved actual usage will be deducted from {selectedTaskInventoryItem.name}. The inventory unit is locked to {selectedTaskInventoryItem.unit}.</small>
                                        )}
                                    </div>
                                    {selectedTaskInventoryItem && (
                                        <>
                                            <div className="workforce-field">
                                                <label htmlFor="assign-task-planned-quantity">Planned Quantity *</label>
                                                <input
                                                    id="assign-task-planned-quantity"
                                                    type="number"
                                                    min="0.001"
                                                    max={Number(selectedTaskInventoryItem.quantity || 0)}
                                                    step="0.001"
                                                    required
                                                    aria-invalid={Boolean(taskAssignmentStockError)}
                                                    className={taskAssignmentStockError ? "workforce-input-error" : ""}
                                                    value={taskForm.planned_quantity}
                                                    onChange={(event) => setTaskForm({...taskForm, planned_quantity:event.target.value})}
                                                />
                                                <small className="workforce-field-help">Available now: <strong>{Number(selectedTaskInventoryItem.quantity || 0).toLocaleString(undefined, { maximumFractionDigits: 3 })} {selectedTaskInventoryItem.unit}</strong>. This amount is only the plan; the worker's actual quantity is reserved at submission and deducted only after approval.</small>
                                                {taskAssignmentStockError && (
                                                    <div className="workforce-stock-warning" role="alert">
                                                        <span className="material-symbols-outlined">warning</span>
                                                        <div>
                                                            <strong>Insufficient Stock</strong>
                                                            <span>{taskAssignmentStockError} Reduce the planned quantity or add stock in Inventory before assigning this task.</span>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                            <div className="workforce-field">
                                                <label htmlFor="assign-task-planned-unit">Inventory Unit</label>
                                                <input id="assign-task-planned-unit" value={selectedTaskInventoryItem.unit || ""} readOnly/>
                                            </div>
                                        </>
                                    )}
                                </div>
                            </section>

                            {taskForm.source_module === "Livestock" && /feed/i.test(`${taskForm.name} ${taskForm.category} ${selectedTaskInventoryItem?.category || ""}`) && (
                                <div className="workforce-field">
                                    <label htmlFor="task-feeding-slot">Feeding Slot</label>
                                    <select id="task-feeding-slot" value={taskForm.feeding_slot || ""} onChange={(event) => setTaskForm({ ...taskForm, feeding_slot: event.target.value })}>
                                        <option value="">Select scheduled feeding</option>
                                        {(taskSourceOptions.find((row) => String(row.id) === String(taskForm.source_record_id))?.feedingSlots || []).map((slot) => <option key={slot}>{slot}</option>)}
                                    </select>
                                    <small>Feeding and harvest assignments update their farm records after review. An existing occurrence is opened from its task.</small>
                                </div>
                            )}
                            <section className="workforce-modal-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">event_available</span>
                                    <div>
                                        <h3>Assignment & Schedule</h3>
                                        <p>Choose who will perform the task and when the work should start.</p>
                                    </div>
                                </div>
                                <div className="workforce-modal-form-grid">
                                    <div className="workforce-field">
                                        <label htmlFor="assign-task-employee">Employee</label>
                                        <select id="assign-task-employee" value={taskForm.employee_id} onChange={(e)=>setTaskForm({...taskForm,employee_id:e.target.value})}>
                                            <option value="">Unassigned</option>
                                            {employees.filter((employee)=>employee.employment_status === "Active").map((employee)=><option key={employee.id} value={employee.id} disabled={!employee.portal_assignment_ready}>{employee.full_name} — {employeePositionLabel(employee)}{employee.portal_assignment_ready ? "" : ` — ${employee.account_status || "No Login Account"}`}</option>)}
                                        </select>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="assign-task-priority">Priority</label>
                                        <select id="assign-task-priority" value={taskForm.priority} onChange={(e)=>setTaskForm({...taskForm,priority:e.target.value})}>
                                            {["Low","Medium","High","Critical"].map((priority)=><option key={priority}>{priority}</option>)}
                                        </select>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="assign-task-date">Date</label>
                                        <input id="assign-task-date" type="date" required value={taskForm.activity_date} onChange={(e)=>setTaskForm({...taskForm,activity_date:e.target.value})}/>
                                    </div>
                                    <div className="workforce-field">
                                        <label htmlFor="assign-task-time">Start Time</label>
                                        <input id="assign-task-time" type="time" value={taskForm.start_time} onChange={(e)=>setTaskForm({...taskForm,start_time:e.target.value})}/>
                                    </div>
                                    <p className="workforce-field full">This creates one dated assignment. Configure repeating crop or livestock care in its management page.</p>
                                    {Boolean(taskForm.employee_id) && <>
                                        <div className="workforce-field">
                                            <label htmlFor="assign-task-backup">Backup Employee</label>
                                            <select id="assign-task-backup" value={taskForm.backup_employee_id} onChange={(e)=>setTaskForm({...taskForm,backup_employee_id:e.target.value})}>
                                                <option value="">Use employee weekly-schedule backup</option>
                                                {employees.filter((employee)=>employee.employment_status === "Active" && String(employee.id)!==String(taskForm.employee_id || "")).map((employee)=><option key={employee.id} value={employee.id} disabled={!employee.portal_assignment_ready}>{employee.full_name}{employee.portal_assignment_ready ? "" : ` — ${employee.account_status || "No Login Account"}`}</option>)}
                                            </select>
                                        </div>
                                        <div className="workforce-field">
                                            <label htmlFor="assign-task-max-delay">Maximum Delay (minutes)</label>
                                            <input id="assign-task-max-delay" type="number" min="0" max="10080" disabled={!taskForm.controlled_rescheduling} value={taskForm.max_delay_minutes} onChange={(e)=>setTaskForm({...taskForm,max_delay_minutes:e.target.value})}/>
                                        </div>
                                        <div className="workforce-modal-checks full">
                                            <label><input type="checkbox" checked={taskForm.time_sensitive} onChange={(e)=>setTaskForm({...taskForm,time_sensitive:e.target.checked})}/><span>Time-sensitive care</span></label>
                                            <label><input type="checkbox" checked={taskForm.controlled_rescheduling} onChange={(e)=>setTaskForm({...taskForm,controlled_rescheduling:e.target.checked,max_delay_minutes:e.target.checked ? taskForm.max_delay_minutes : ""})}/><span>Allow controlled rescheduling</span></label>
                                        </div>
                                    </>}
                                </div>
                            </section>

                            <section className="workforce-modal-section">
                                <div className="workforce-modal-section-title">
                                    <span className="material-symbols-outlined">fact_check</span>
                                    <div>
                                        <h3>Instructions & Review</h3>
                                        <p>Give the employee clear instructions and choose what must be submitted for verification.</p>
                                    </div>
                                </div>
                                <div className="workforce-modal-form-grid">
                                    <div className="workforce-field full">
                                        <label htmlFor="assign-task-instructions">Instructions</label>
                                        <textarea id="assign-task-instructions" value={taskForm.instructions} onChange={(e)=>setTaskForm({...taskForm,instructions:e.target.value})}/>
                                    </div>
                                    <div className="workforce-modal-checks full">
                                        <label>
                                            <input type="checkbox" checked={Boolean(taskForm.employee_id) || taskForm.requires_review} disabled={Boolean(taskForm.employee_id) || ["Weight Monitoring", "Crop Growth Monitoring"].includes(taskForm.category)} onChange={(e)=>setTaskForm({...taskForm,requires_review:e.target.checked})}/>
                                            <span>{taskForm.employee_id ? "Manager review is required for assigned work" : "Requires manager review"}</span>
                                        </label>
                                        <label>
                                            <input type="checkbox" checked={taskForm.requires_evidence} disabled={["Weight Monitoring", "Crop Growth Monitoring"].includes(taskForm.category)} onChange={(e)=>setTaskForm({...taskForm,requires_evidence:e.target.checked})}/>
                                            <span>Requires evidence</span>
                                        </label>
                                    </div>
                                </div>
                            </section>

                            <footer className="workforce-modal-footer">
                                <button type="button" className="workforce-modal-cancel" onClick={closeTaskModal}>
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="workforce-modal-save"
                                    disabled={taskSaving || Boolean(taskAssignmentStockError)}
                                    title={taskAssignmentStockError || "Save assignment"}
                                >
                                    <span className="material-symbols-outlined">assignment_add</span>
                                    {taskSaving ? "Saving…" : taskAssignmentStockError ? "Check Resource" : "Save Assignment"}
                                </button>
                            </footer>
                            </fieldset>
                        </form>
                    </div>
                </div>
            )}
        </>
    );
}

export default TaskManagementModals;
