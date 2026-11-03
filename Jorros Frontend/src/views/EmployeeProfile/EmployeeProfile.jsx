"use client";

import { useEffect, useState } from "react";

import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import PageState from "../../components/Common/PageState.jsx";
import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import { workforceService } from "../../services/workforceService.js";
import "./EmployeeProfile.css";

const displayValue = (value) => {
    const text = String(value ?? "").trim();
    return text || "—";
};

const statusClass = (value) =>
    String(value || "")
        .trim()
        .toLowerCase()
        .replaceAll(" ", "-");

export default function EmployeeProfile() {
    const [profile, setProfile] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        let active = true;

        workforceService
            .getMyProfile()
            .then((result) => {
                if (active) setProfile(result);
            })
            .catch((requestError) => {
                if (active) {
                    setError(
                        requestError?.message ||
                            "Unable to load your employee profile."
                    );
                }
            })
            .finally(() => {
                if (active) setLoading(false);
            });

        return () => {
            active = false;
        };
    }, []);

    const detailRows = [
        ["Username", profile?.username, "alternate_email"],
        ["Assigned Area", profile?.assigned_area, "location_on"],
        ["Contact Number", profile?.contact_number, "call"],
        ["Email", profile?.email, "mail"],
    ];

    return (
        <div className="workforce-layout employee-profile-layout">
            <Sidebar />

            <main className="employee-profile-page">
                <header className="employee-profile-header">
                    <div className="employee-profile-heading">
                        <h1>My Profile</h1>
                        <p>
                            View your employee information and account details.
                        </p>
                    </div>

                    <AppHeaderActions />
                </header>

                {loading ? (
                    <section className="employee-profile-state-card">
                        <PageState
                            compact
                            type="loading"
                            title="Loading Profile"
                            message="Preparing your employee information."
                        />
                    </section>
                ) : error ? (
                    <section className="employee-profile-state-card">
                        <PageState
                            compact
                            type="error"
                            title="Profile unavailable"
                            message={error}
                        />
                    </section>
                ) : (
                    <div className="employee-profile-content">
                        <section
                            className="employee-profile-overview-card"
                            aria-labelledby="employee-profile-overview-title"
                        >
                            <div className="employee-profile-avatar" aria-hidden="true">
                                <span className="material-symbols-outlined">person</span>
                            </div>

                            <div className="employee-profile-overview-copy">
                                <span className="employee-profile-eyebrow">
                                    Employee Profile
                                </span>
                                <h2 id="employee-profile-overview-title">
                                    {displayValue(profile?.full_name)}
                                </h2>
                                <div className="employee-profile-overview-meta">
                                    <span>{displayValue(profile?.employee_code)}</span>
                                    <span aria-hidden="true">•</span>
                                    <span>{displayValue(profile?.position)}</span>
                                </div>
                            </div>

                            <span
                                className={`employee-profile-status ${statusClass(
                                    profile?.employment_status
                                )}`}
                            >
                                {displayValue(profile?.employment_status)}
                            </span>
                        </section>

                        <section
                            className="employee-profile-card"
                            aria-labelledby="employee-profile-information-title"
                        >
                            <div className="employee-profile-section-heading">
                                <div className="employee-profile-section-icon" aria-hidden="true">
                                    <span className="material-symbols-outlined">
                                        badge
                                    </span>
                                </div>
                                <div>
                                    <h2 id="employee-profile-information-title">
                                        Employee Information
                                    </h2>
                                    <p>
                                        Information used for your Joross Farm work account.
                                    </p>
                                </div>
                            </div>

                            <dl className="employee-profile-detail-grid">
                                {detailRows.map(([label, value, icon]) => (
                                    <div className="employee-profile-detail" key={label}>
                                        <span
                                            className="material-symbols-outlined employee-profile-detail-icon"
                                            aria-hidden="true"
                                        >
                                            {icon}
                                        </span>
                                        <div>
                                            <dt>{label}</dt>
                                            <dd>{displayValue(value)}</dd>
                                        </div>
                                    </div>
                                ))}
                            </dl>

                            <div className="employee-profile-note" role="note">
                                <span className="material-symbols-outlined" aria-hidden="true">
                                    info
                                </span>
                                <p>
                                    Contact a manager or administrator if this information needs to be corrected.
                                </p>
                            </div>
                        </section>
                    </div>
                )}
            </main>
        </div>
    );
}
