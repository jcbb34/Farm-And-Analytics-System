'use client';
import { useEffect } from 'react';
import { useAuth } from '../../context/AuthContext.jsx';
import { notifyWarning } from '../../context/NotificationContext.jsx';
import { backupRecoveryService } from '../../services/backupRecoveryService.js';
export default function BackupReminderNotice() {
    const { user, hasPermission } = useAuth();
    useEffect(() => {
        if (!user?.id || !hasPermission('*')) return;
        let active = true;
        const check = async () => {
            try {
                const notices = await backupRecoveryService.notices();
                for (const item of notices) {
                    const key = 'backup-notice-' + user.id + '-' + item.id;
                    if (active && !sessionStorage.getItem(key)) { sessionStorage.setItem(key, 'seen'); notifyWarning(item.message); }
                }
            } catch { /* The recovery panel displays connection errors with retry controls. */ }
        };
        check(); const timer = setInterval(check, 60000);
        return () => { active = false; clearInterval(timer); };
    }, [user?.id, hasPermission]);
    return null;
}
