"use client";

import {
    createContext,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";

const ThemeContext = createContext(null);

const THEME_STORAGE_KEY = "joross-theme";

function getInitialTheme() {
    if (typeof window === "undefined") {
        return "light";
    }

    try {
        const savedTheme =
            localStorage.getItem(
                THEME_STORAGE_KEY
            );

        if (
            savedTheme === "light" ||
            savedTheme === "dark"
        ) {
            return savedTheme;
        }
    } catch {
        // Continue with the default theme.
    }

    return "light";
}

export function ThemeProvider({
    children,
}) {
    const [theme, setTheme] =
        useState(getInitialTheme);

    useEffect(() => {
        const root =
            document.documentElement;

        root.setAttribute(
            "data-theme",
            theme
        );

        root.style.colorScheme =
            theme;

        document.body.classList.toggle(
            "dark-mode",
            theme === "dark"
        );

        try {
            localStorage.setItem(
                THEME_STORAGE_KEY,
                theme
            );
        } catch {
            // The theme still works when storage is unavailable.
        }
    }, [theme]);

    const value = useMemo(
        () => ({
            theme,
            isDarkMode:
                theme === "dark",
            setTheme,
            toggleTheme: () => {
                setTheme(
                    (currentTheme) =>
                        currentTheme ===
                        "dark"
                            ? "light"
                            : "dark"
                );
            },
        }),
        [theme]
    );

    return (
        <ThemeContext.Provider
            value={value}
        >
            {children}
        </ThemeContext.Provider>
    );
}

export function useTheme() {
    const context =
        useContext(ThemeContext);

    if (!context) {
        throw new Error(
            "useTheme must be used inside ThemeProvider."
        );
    }

    return context;
}
