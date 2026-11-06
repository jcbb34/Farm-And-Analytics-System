import { serveSessionPolicy } from './helpers/serveSessionPolicy.mjs';
import { test, expect } from "@playwright/test";

const initialDetails = { first_name: "Casey Ana", middle_name: "Reyes", surname: "De la Cruz", suffix: "Jr.", address: { street: "12 Sample Street", subdivision: "Sample Village", province: "Custom Province", province_code: null, city: "Custom City", city_code: null, barangay: "Custom Barangay", barangay_code: null, postal_code: "0450" } };
const current = { id: 77, user_code: "USR-TEST", username: "casey.admin", full_name: "Casey Ana Reyes De la Cruz Jr.", email: "account.profile.synthetic@gmail.com", contact_number: "09123456789", position: "Farm Administrator", role: { name: "System Administrator", permissions: ["*"] }, permissions: ["*"], status: "Active", personal_details: initialDetails, two_factor_enabled: false };

async function setup(page) {
    await page.mouse.move(1400, 700);
    let record = structuredClone(current);
    let other = { ...structuredClone(current), id: 78, username: "other.admin", user_code: "USR-OTHER", full_name: "Other Administrator", email: "other.profile.synthetic@gmail.com", personal_details: null };
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => {
        if (!sessionStorage.getItem("joross-auth-session-v1")) sessionStorage.setItem("joross-auth-session-v1", JSON.stringify({ accessToken: "synthetic-account-profile", expiresAt: Date.now() + 86400000, user: { id: 77, username: "casey.admin", fullName: "Stale profile", role: "System Administrator", permissions: ["*"], status: "Active" } }));
    });
    await page.route("**/api/v1/**", async route => {
        if (await serveSessionPolicy(route, page)) return;
        const request = route.request(), path = new URL(request.url()).pathname;
        if (path.endsWith("/events/stream")) return route.fulfill({ status: 503, json: {} });
        if (path === "/api/v1/auth/me") return route.fulfill({ json: record });
        if (path === "/api/v1/users") return route.fulfill({ json: [record, other] });
        if (path === "/api/v1/roles") return route.fulfill({ json: [{ id: 1, name: "System Administrator", permissions: ["*"], is_active: true }] });
        if (["/api/v1/users/77", "/api/v1/users/78"].includes(path) && request.method() === "PUT") {
            const body = request.postDataJSON();
            const updated = { ...(path.endsWith("77") ? record : other), ...body, role: { name: body.role_name || "System Administrator" } };
            if (body.personal_details?.first_name && body.personal_details?.surname) updated.full_name = [body.personal_details.first_name, body.personal_details.middle_name, body.personal_details.surname, body.personal_details.suffix].filter(Boolean).join(" ");
            if (path.endsWith("77")) record = updated; else other = updated;
            return route.fulfill({ json: updated });
        }
        if (path.includes("/archives")) return route.fulfill({ json: { items: [], counts: {}, total: 0 } });
        return route.fulfill({ json: [] });
    });
    return { errors, current: () => record };
}

function accountField(page, name) {
    return page.locator(".settings-page-account-detail").filter({ has: page.locator("dt").getByText(name, { exact: true }) }).locator("dd");
}

async function editUser(page, username = "casey.admin") {
    await page.mouse.move(1400, 700);
    await expect(page.locator(".sidebar")).toHaveCSS("width", "80px");
    await page.getByRole("button", { name: /User Management/ }).click();
    const row = page.getByRole("row").filter({ hasText: `@${username}` });
    await row.getByTitle("Edit user", { exact: true }).click();
    return page.getByRole("dialog", { name: "Edit User Account", exact: true });
}

test("Account displays the same names, address and access fields as the selected User Management record", async ({ page }) => {
    const state = await setup(page);
    await page.goto("/settings");
    for (const [label, value] of [["First name", "Casey Ana"], ["Middle name (optional)", "Reyes"], ["Surname", "De la Cruz"], ["Suffix (optional)", "Jr."], ["Email Address", "account.profile.synthetic@gmail.com"], ["Contact Number", "09123456789"], ["Position", "Farm Administrator"], ["House/Building Number and Street", "12 Sample Street"], ["Province / address area", "Custom Province"], ["City / Municipality", "Custom City"], ["Barangay", "Custom Barangay"], ["Postal / ZIP Code", "0450"], ["User Code", "USR-TEST"], ["Username", "casey.admin"], ["Account Status", "Active"]]) {
        await expect(accountField(page, label)).toHaveText(value);
    }
    const dialog = await editUser(page);
    await expect(dialog.getByLabel("First name", { exact: false })).toHaveValue("Casey Ana");
    await expect(dialog.getByLabel("Surname", { exact: false })).toHaveValue("De la Cruz");
    await expect(dialog.getByLabel("Postal / ZIP Code", { exact: true })).toHaveValue("0450");
    await expect(dialog.locator("#userRole")).toHaveValue("System Administrator");
    expect(state.errors).toEqual([]);
});

test("editing the current user updates Account and the saved session without another sign-in", async ({ page }) => {
    const state = await setup(page);
    await page.goto("/settings");
    await expect(accountField(page, "First name")).toHaveText("Casey Ana");
    const dialog = await editUser(page);
    await dialog.getByLabel("First name", { exact: false }).fill("Casey Marie");
    await dialog.locator("#userContactNumber").fill("09987654321");
    await dialog.locator("#userPosition").fill("Farm Operations Manager");
    await dialog.getByLabel("House/Building Number and Street", { exact: true }).fill("34 Updated Street");
    await dialog.getByRole("button", { name: "Save Changes", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await page.getByRole("button", { name: /^person\s+Account/ }).click();
    await expect(accountField(page, "First name")).toHaveText("Casey Marie");
    await expect(accountField(page, "Contact Number")).toHaveText("09987654321");
    await expect(accountField(page, "Position")).toHaveText("Farm Operations Manager");
    await expect(accountField(page, "House/Building Number and Street")).toHaveText("34 Updated Street");
    expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("joross-auth-session-v1")).user.personalDetails.first_name)).toBe("Casey Marie");
    await page.reload();
    await expect(accountField(page, "First name")).toHaveText("Casey Marie");
    expect(state.current().personal_details.first_name).toBe("Casey Marie");
    expect(state.errors).toEqual([]);
});

test("editing a different user leaves the signed-in account information intact", async ({ page }) => {
    await setup(page);
    await page.goto("/settings");
    await expect(accountField(page, "First name")).toHaveText("Casey Ana");
    const dialog = await editUser(page, "other.admin");
    await dialog.locator("#userPosition").fill("Other Account Position");
    await dialog.getByRole("button", { name: "Save Changes", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await page.getByRole("button", { name: /^person\s+Account/ }).click();
    await expect(accountField(page, "Username")).toHaveText("casey.admin");
    await expect(accountField(page, "Position")).toHaveText("Farm Administrator");
});
