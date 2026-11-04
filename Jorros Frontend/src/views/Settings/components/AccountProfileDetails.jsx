function Detail({ label, value, wide = false, children, fallback = "Not provided" }) {
    return (
        <div className={`settings-page-account-detail${wide ? " full-width" : ""}`}>
            <dt>{label}</dt>
            <dd>{value || fallback}{children}</dd>
        </div>
    );
}

// Match the fields and grouping in User Management without making the profile editable.
export default function AccountProfileDetails({ profile }) {
    const details = profile.personalDetails || {};
    const address = details.address || {};
    return (
        <div className="settings-page-account-groups">
            <section className="settings-page-account-group" aria-labelledby="accountPersonalInformation">
                <div className="settings-page-account-group-heading">
                    <span className="material-symbols-outlined" aria-hidden="true">badge</span>
                    <h3 id="accountPersonalInformation">Personal Information</h3>
                </div>
                <dl className="settings-page-account-details" aria-label="Personal information">
                    {!details.first_name && !details.surname && (
                        <Detail label="Full Name" value={profile.fullName} wide />
                    )}
                    <Detail label="First name" value={details.first_name} />
                    <Detail label="Middle name (optional)" value={details.middle_name} />
                    <Detail label="Surname" value={details.surname} />
                    <Detail label="Suffix (optional)" value={details.suffix} fallback="None" />
                    <Detail label="Email Address" value={profile.email} />
                    <Detail label="Contact Number" value={profile.contactNumber} />
                    <Detail label="Position" value={profile.position} wide />
                </dl>

                <h4 className="settings-page-account-address-heading">Address <small>(optional)</small></h4>
                <dl className="settings-page-account-details" aria-label="Address">
                    <Detail label="House/Building Number and Street" value={address.street} wide />
                    <Detail label="Subdivision, Village, or Building Name (optional)" value={address.subdivision} wide />
                    <Detail label="Province / address area" value={address.province} />
                    <Detail label="City / Municipality" value={address.city} />
                    <Detail label="Barangay" value={address.barangay} />
                    <Detail label="Postal / ZIP Code" value={address.postal_code} />
                </dl>
            </section>

            <section className="settings-page-account-group" aria-labelledby="accountAccessInformation">
                <div className="settings-page-account-group-heading">
                    <span className="material-symbols-outlined" aria-hidden="true">security</span>
                    <h3 id="accountAccessInformation">Account and Access</h3>
                </div>
                <dl className="settings-page-account-details" aria-label="Account and access">
                    <Detail label="User Code" value={profile.userCode} />
                    <Detail label="Username" value={profile.username} />
                    <Detail label="Role" value={profile.role} fallback="Not assigned">
                        <small>Managed by System Administrator</small>
                    </Detail>
                    <Detail label="Account Status" value={profile.status} />
                </dl>
            </section>
        </div>
    );
}
