// Left-side navigation for the settings categories
export default function SettingsSectionMenu({
    sections,
    activeSection,
    onChange,
}) {
    return (
        <aside className="settings-page-section-menu">
            <div className="settings-page-menu-heading">
                <strong>Settings Menu</strong>
                <small>Select a settings category</small>
            </div>

            {sections.map((section) => (
                <button
                    type="button"
                    key={section.id}
                    className={activeSection === section.id ? "active" : ""}
                    onClick={() => onChange(section.id)}
                >
                    <span className="material-symbols-outlined">{section.icon}</span>

                    <span>
                        <strong>{section.label}</strong>
                        <small>{section.description}</small>
                    </span>
                </button>
            ))}
        </aside>
    );
}
