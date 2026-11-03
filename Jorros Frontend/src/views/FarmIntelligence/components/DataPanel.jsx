"use client";

import { useRouter } from "next/navigation";

// Data import and database backup links.
export default function DataPanel({ isAdmin, canImport }) {
    const router = useRouter();

    return (
        <div className="fi-panel-stack">
            <section className="fi-card fi-data-link">
                <span className="material-symbols-outlined">
                    upload_file
                </span>

                <div>
                    <h3>Smart Data Import</h3>
                    <p>
                        Spreadsheet imports are validated by FastAPI and
                        committed to Microsoft SQL Server. Imported Crop,
                        Livestock, and Inventory records therefore appear on
                        every authorized computer, not only in this browser.
                    </p>
                </div>

                <button
                    type="button"
                    className="fi-primary-button"
                    disabled={!canImport}
                    onClick={() =>
                        router.push(
                            "/settings?section=data&action=import"
                        )
                    }
                >
                    <span className="material-symbols-outlined">
                        database_upload
                    </span>
                    Open Smart Import
                </button>
            </section>

            <section className="fi-card fi-data-link">
                <span className="material-symbols-outlined">
                    backup
                </span>

                <div>
                    <h3>Database Backup</h3>
                    <p>
                        Backups are created from the server-side SQL Server
                        data. Browser localStorage snapshots are no longer used,
                        preventing nested backups and computer-specific copies.
                    </p>
                </div>

                <button
                    type="button"
                    className="fi-secondary-button"
                    disabled={!isAdmin}
                    onClick={() =>
                        router.push(
                            "/settings?section=data"
                        )
                    }
                >
                    Open Database Backup
                </button>
            </section>

            {!isAdmin && !canImport && (
                <div className="fi-disclaimer compact">
                    <span className="material-symbols-outlined">
                        lock
                    </span>
                    <span>
                        Smart Import requires import permission. Database backups remain limited to the System Administrator.
                    </span>
                </div>
            )}
        </div>
    );
}

