import AppHeaderActions from "../../../components/AppHeaderActions/AppHeaderActions.jsx";

// Settings page title and account actions
function SettingsHeader() {
    return (
        <header className="settings-page-header">
            <div className="settings-page-heading">
                <h1>System Settings</h1>
                <p>
                    Manage accounts, users, security, system data,
                    notifications, and archived records.
                </p>
            </div>

            <AppHeaderActions />
        </header>
    );
}

export default SettingsHeader;
