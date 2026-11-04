"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "../../context/AuthContext.jsx";
import { useUnsavedChanges } from "../../context/UnsavedChangesContext.jsx";
import {
    isTaskOnlyUser,
    TASK_HOME_ROUTE,
} from "../../utils/accessControl.js";

import "./Sidebar.css";

const menuItems = [
    {
        name: "Dashboard",
        icon: "home",
        path: "/dashboard",
        permission: "dashboard:view",
    },
    {
        name: "My Tasks",
        icon: "task_alt",
        path: TASK_HOME_ROUTE,
        permission: "workforce:submit",
        taskOnlyOnly: true,
    },
    {
        name: "My Profile",
        icon: "person",
        path: "/profile",
        permission: "workforce:submit",
        taskOnlyOnly: true,
    },
    {
        name: "Task Management",
        icon: "assignment",
        path: "/task-management",
        permission: "workforce:manage",
    },
    {
        name: "Staff Calendar",
        icon: "calendar_month",
        path: "/staff-calendar",
        permission: "workforce:attendance",
    },
    {
        name: "Crops",
        icon: "grass",
        path: "/crops",
        permission: "crops:view",
    },
    {
        name: "Livestock",
        icon: "pets",
        path: "/livestock",
        permission: "livestock:view",
    },
    {
        name: "Production & Sales",
        icon: "point_of_sale",
        path: "/production-sales",
        permission: "production_sales:view",
    },
    {
        name: "Alerts",
        icon: "notifications",
        path: "/alerts",
        permission: "alerts:view",
    },
    {
        name: "Reports",
        icon: "monitoring",
        path: "/reports",
        permission: "reports:view",
    },
    {
        name: "Farm Intelligence",
        icon: "psychology_alt",
        path: "/intelligence",
        permission: "intelligence:view",
    },
    {
        name: "Inventory",
        icon: "inventory_2",
        path: "/inventory",
        permission: "inventory:view",
    },
    {
        name: "System Settings",
        icon: "settings",
        path: "/settings",
        permission: "*",
    },
];

function Sidebar() {
    const pathname = usePathname();
    const { hasPermission, user } = useAuth();
    const { requestNavigation } = useUnsavedChanges();

    const visibleMenuItems = menuItems.filter((item) => {
        if (!hasPermission(item.permission)) return false;
        if (item.taskOnlyOnly && !isTaskOnlyUser(user)) return false;
        return true;
    });

    const handleNavigation = async (event, path) => {
        event.preventDefault();

        if (pathname === path) {
            return;
        }

        await requestNavigation(path);
    };

    const taskOnlyMode = isTaskOnlyUser(user);

    return (
        <aside className={`sidebar ${taskOnlyMode ? "sidebar-task-only" : ""}`}>
            <div className="sidebar-container">
                <div className="sidebar-brand">
                    <div className="logo-wrapper">
                        <img
                            src="/images/Jorros Logo 2.png"
                            alt="Jorros Farm Logo"
                            className="brand-logo-img"
                        />
                    </div>
                </div>

                <nav aria-label="Main navigation">
                    <ul className="sidebar-menu">
                        {visibleMenuItems.map((item) => (
                            <li key={item.name}>
                                <Link
                                    href={item.path}
                                    aria-label={item.name}
                                    title={item.name}
                                    onClick={(event) =>
                                        handleNavigation(
                                            event,
                                            item.path
                                        )
                                    }
                                    className={
                                        pathname === item.path
                                            ? "sidebar-item active"
                                            : "sidebar-item"
                                    }
                                >
                                    <span className="material-symbols-outlined" aria-hidden="true">
                                        {item.icon}
                                    </span>

                                    <span className="item-text">
                                        {item.name}
                                    </span>
                                </Link>
                            </li>
                        ))}
                    </ul>
                </nav>
            </div>

        </aside>
    );
}

export default Sidebar;
