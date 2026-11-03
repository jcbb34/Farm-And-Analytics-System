import AppHeaderActions from "../../../components/AppHeaderActions/AppHeaderActions.jsx";

// Reports page title and account actions
export default function ReportsHeader() {
    return (
        <header className="reports-page-header">
            <div className="reports-page-heading">
                <h1>Reports Management</h1>
                <p>
                    Generate and review crop, livestock, production and sales, inventory, and trend & seasonal reports.
                </p>
            </div>

            <div className="reports-page-header-actions">
                <AppHeaderActions />
            </div>
        </header>
    );
}
