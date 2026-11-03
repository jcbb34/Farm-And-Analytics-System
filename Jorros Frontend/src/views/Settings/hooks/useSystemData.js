import { notify } from "../../../context/NotificationContext.jsx";
import { useEffect, useState } from "react";

import { backupService } from "../../../services/backupService.js";
import {
    confirmAction,
    notifyWarning,
} from "../../../context/NotificationContext.jsx";

// Handles backup, export, and reset actions for System Data.
function downloadFile(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

export function useSystemData({
    enabled,
    onResetPreferences,
}) {
    const [backups, setBackups] = useState([]);
    const [backupLoading, setBackupLoading] = useState(false);
    const [backupCreating, setBackupCreating] = useState(false);
    const [backupError, setBackupError] = useState("");

    useEffect(() => {
        let cancelled = false;

        if (!enabled) {
            setBackups([]);
            setBackupError("");
            return undefined;
        }

        const loadBackups = async () => {
            try {
                setBackupLoading(true);
                setBackupError("");

                const records = await backupService.getBackups(50);

                if (!cancelled) {
                    setBackups(records);
                }
            } catch (error) {
                if (!cancelled) {
                    console.error("Failed to load backup history:", error);
                    setBackupError(
                        error?.message || "Unable to load backup history."
                    );
                }
            } finally {
                if (!cancelled) {
                    setBackupLoading(false);
                }
            }
        };

        loadBackups();

        return () => {
            cancelled = true;
        };
    }, [enabled]);

    const exportSystemData = async () => {
        if (!enabled) {
            notifyWarning(
                "Only a System Administrator can export the database."
            );
            return;
        }

        try {
            const backup = await backupService.createBackup();
            const content = await backupService.getBackupContent(backup.id);

            setBackups((currentBackups) => [
                backup,
                ...currentBackups.filter(
                    (record) => record.id !== backup.id
                ),
            ]);

            downloadFile(
                JSON.stringify(content, null, 2),
                backup.filename || `${backup.backupCode}.json`,
                "application/json"
            );

            notify(
                "Current SQL Server application data exported successfully."
            );
        } catch (error) {
            console.error("Failed to export system data:", error);
            notify(
                error?.message || "Unable to export the system database."
            );
        }
    };

    const createBackup = async () => {
        if (!enabled) {
            notifyWarning(
                "Only a System Administrator can create database backups."
            );
            return;
        }

        const confirmed = await confirmAction({
            title: "Create Database Backup",
            message:
                "Back up the current Joross Farm database together with task evidence photos and thumbnails?",
            type: "warning",
            confirmText: "Create Backup",
            cancelText: "Cancel",
        });

        if (!confirmed) {
            return;
        }

        try {
            setBackupCreating(true);
            setBackupError("");

            const backup = await backupService.createBackup();

            setBackups((currentBackups) => [
                backup,
                ...currentBackups.filter(
                    (record) => record.id !== backup.id
                ),
            ]);

            notify(
                `Database backup ${backup.backupCode} created successfully.`
            );
        } catch (error) {
            console.error("Failed to create database backup:", error);
            setBackupError(
                error?.message || "Unable to create database backup."
            );
            notify(
                error?.message || "Unable to create database backup."
            );
        } finally {
            setBackupCreating(false);
        }
    };

    const downloadBackup = async (backup) => {
        try {
            if (backup.recoveryAvailable) {
                const content = await backupService.getRecoveryPackage(backup.id);
                downloadFile(content, `${backup.backupCode}.recovery.zip`, "application/zip");
                return;
            }
            const content = await backupService.getBackupContent(backup.id);

            downloadFile(
                JSON.stringify(content, null, 2),
                backup.filename || `${backup.backupCode}.json`,
                "application/json"
            );
        } catch (error) {
            console.error("Failed to download backup:", error);
            notify(
                error?.message || "Unable to download the backup."
            );
        }
    };

    const resetSystemData = async () => {
        const confirmed = await confirmAction({
            title: "Reset Interface Preferences",
            message:
                "Reset notification and display preferences on this browser? Database records, accounts, roles, and farm data will not be deleted.",
            type: "warning",
            confirmText: "Reset Preferences",
            cancelText: "Cancel",
        });

        if (!confirmed) {
            return;
        }

        onResetPreferences?.();

        notify(
            "Interface preferences reset successfully. Farm database records were not changed."
        );
    };

    return {
        backups,
        backupLoading,
        backupCreating,
        backupError,
        exportSystemData,
        createBackup,
        downloadBackup,
        resetSystemData,
    };
}
