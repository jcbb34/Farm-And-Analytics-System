import { useEffect, useMemo, useState } from "react";

import { notifyWarning } from "../../../context/NotificationContext.jsx";
import { settingSections } from "../settingsConfig.js";

// Handles Settings section navigation and URL actions
export function useSettingsNavigation({
    locationSearch,
    isSystemAdministrator,
    canUseSmartImport,
    profileDetailsRef,
    accountSecurityRef,
    onOpenSmartImport,
}) {
    const [activeSection, setActiveSection] = useState("account");

    const visibleSettingSections = useMemo(
        () =>
            settingSections.filter(
                (section) =>
                    !section.administratorOnly || isSystemAdministrator
            ),
        [isSystemAdministrator]
    );

    useEffect(() => {
        const searchParams = new URLSearchParams(locationSearch);
        const requestedSection = searchParams.get("section");
        const requestedFocus = searchParams.get("focus");
        const requestedAction = searchParams.get("action");

        const validSections = visibleSettingSections.map(
            (section) => section.id
        );

        const requestedSectionConfig = settingSections.find(
            (section) => section.id === requestedSection
        );

        if (
            requestedSectionConfig?.administratorOnly &&
            !isSystemAdministrator
        ) {
            setActiveSection("account");
            notifyWarning(
                "Only a System Administrator can access this settings section."
            );
        } else if (
            requestedFocus === "profile" ||
            requestedFocus === "security"
        ) {
            setActiveSection("account");
        } else if (
            requestedSection &&
            validSections.includes(requestedSection)
        ) {
            setActiveSection(requestedSection);
        }

        if (requestedAction === "import" && canUseSmartImport) {
            if (isSystemAdministrator) {
                setActiveSection("data");
            }
            onOpenSmartImport();
        }

        if (!requestedFocus) {
            return undefined;
        }

        const scrollTimer = window.setTimeout(() => {
            const target =
                requestedFocus === "security"
                    ? accountSecurityRef.current
                    : profileDetailsRef.current;

            target?.scrollIntoView({
                behavior: "smooth",
                block: "start",
            });
        }, 120);

        return () => window.clearTimeout(scrollTimer);
    }, [
        locationSearch,
        isSystemAdministrator,
        canUseSmartImport,
        visibleSettingSections,
        profileDetailsRef,
        accountSecurityRef,
        onOpenSmartImport,
    ]);

    useEffect(() => {
        const activeSectionConfig = settingSections.find(
            (section) => section.id === activeSection
        );

        if (
            !isSystemAdministrator &&
            activeSectionConfig?.administratorOnly
        ) {
            setActiveSection("account");
            notifyWarning(
                "Only a System Administrator can access this settings section."
            );
        }
    }, [activeSection, isSystemAdministrator]);

    return {
        activeSection,
        setActiveSection,
        visibleSettingSections,
    };
}
