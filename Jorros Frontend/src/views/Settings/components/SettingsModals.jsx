import { SmartImportModal } from "../../../components/SmartImport/SmartImport.jsx";
import ChangePasswordModal from "./ChangePasswordModal.jsx";
import TwoFactorSetupModal from "./TwoFactorSetupModal.jsx";

// Modals used by the Settings page
function SettingsModals({
    smartImportOpen,
    isSystemAdministrator,
    onCloseSmartImport,
    onSmartImportComplete,
    twoFactorSetup,
    onCloseTwoFactorSetup,
    onTwoFactorEnabled,
    passwordModalOpen,
    onClosePasswordModal,
}) {
    return (
        <>
            <SmartImportModal
                open={smartImportOpen}
                isAdministrator={isSystemAdministrator}
                onClose={onCloseSmartImport}
                onComplete={onSmartImportComplete}
            />

            <TwoFactorSetupModal
                open={Boolean(twoFactorSetup)}
                setup={twoFactorSetup}
                onClose={onCloseTwoFactorSetup}
                onEnabled={onTwoFactorEnabled}
            />

            <ChangePasswordModal
                open={passwordModalOpen}
                onClose={onClosePasswordModal}
            />
        </>
    );
}

export default SettingsModals;
