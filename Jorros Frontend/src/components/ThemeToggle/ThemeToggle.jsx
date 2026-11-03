"use client";

import { useTheme } from "../../context/ThemeContext.jsx";

import "./ThemeToggle.css";

function ThemeToggle({ className = "" }) {
    const { isDarkMode, toggleTheme } = useTheme();

    return (
        <button
            type="button"
            className={`theme-toggle ${
                isDarkMode ? "dark" : "light"
            } ${className}`.trim()}
            role="switch"
            aria-checked={isDarkMode}
            aria-label={
                isDarkMode
                    ? "Switch to light mode"
                    : "Switch to dark mode"
            }
            title={
                isDarkMode
                    ? "Switch to light mode"
                    : "Switch to dark mode"
            }
            onClick={toggleTheme}
        >
            <span
                className="material-symbols-outlined theme-toggle-sun"
                aria-hidden="true"
            >
                light_mode
            </span>

            <span
                className="material-symbols-outlined theme-toggle-moon"
                aria-hidden="true"
            >
                dark_mode
            </span>

            <span
                className="theme-toggle-thumb"
                aria-hidden="true"
            >
                <span className="material-symbols-outlined">
                    {isDarkMode ? "dark_mode" : "light_mode"}
                </span>
            </span>
        </button>
    );
}

export default ThemeToggle;
