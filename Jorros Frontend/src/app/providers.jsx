"use client";

import { ThemeProvider } from "../context/ThemeContext.jsx";
import { NotificationProvider } from "../context/NotificationContext.jsx";
import { AuthProvider } from "../context/AuthContext.jsx";
import { UnsavedChangesProvider } from "../context/UnsavedChangesContext.jsx";
import { AppHeaderProvider } from "../context/AppHeaderContext.jsx";
import PwaBootstrap from "../components/PWA/PwaBootstrap.jsx";
import { VoidAuthorizationProvider } from "../context/VoidAuthorizationContext.jsx";
import BackupReminderNotice from "../components/BackupRecovery/BackupReminderNotice.jsx";
import RealTimeProvider from "../context/RealTimeProvider.jsx";

export default function Providers({ children }) {
    return (
        <>
            <PwaBootstrap />
            <ThemeProvider>
            <NotificationProvider>
                <AuthProvider>
                    <BackupReminderNotice/>
                    <VoidAuthorizationProvider>
                    <UnsavedChangesProvider>
                        <AppHeaderProvider>
                            <RealTimeProvider>
                            {children}
                            </RealTimeProvider>
                        </AppHeaderProvider>
                    </UnsavedChangesProvider>
                    </VoidAuthorizationProvider>
                </AuthProvider>
            </NotificationProvider>
            </ThemeProvider>
        </>
    );
}
