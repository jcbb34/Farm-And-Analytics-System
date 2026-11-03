import { test, expect } from "@playwright/test";

// The browser tests intercept API traffic so they never connect to, or write
// into, the operator's database. Backend tests cover real bearer authorization.
const user = {
    id: 1, userCode: "QR-VIEWER", username: "qr.viewer", fullName: "QR Test Viewer",
    role: "Viewer", permissions: ["dashboard:view"], status: "Active",
};
const image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAQgAAAEIAQAAAACLjVdSAAABUUlEQVR4nO2YQY5CMQxD/dDc/8pmkbSdj0CsJj+jFrGA6i0sK0mdYn35PL4BhzjEITYlfiSJ+G0hS0ieJ32UFvohSxJCEjaeJ2U6uhDhh0gHxLhv5kkXpbcQlsTolht19CCcX38kanTcSGS/pAMmCmSd9FFa6Uc2CJYwxlot00VpoR+rP8xLdfRRWkhEMSBFAJFBAqp1NCDWfZtzFGO0bb8EQYTT4Yplx0mxji6EbWyERm3MjNpM6V8TMU+RY3lBDk9WUO2itHKfc3aMY6IazRzSRmktYZm8aUFGsPc+Z3kUSl43ucd0UVrqR8wMR/iImToW3C5Kawj85k/k9lIdXYjL+9haXIirZvP3Mc0J4vVm2EVpdV6fjWMRq8yO+8uVMAbJtjbNp1di7DGw9Tz9/d7BmB1jw+2itNKP+T7GcCEje5mOLsQlf9yo4xCHOMT/I57ncXUsxTIdmgAAAABJRU5ErkJggg==";
const link = (url, kind = "lan") => ({ kind, label: kind === "lan" ? "Same Wi-Fi / LAN" : "Tailscale", url, qrDataUrl: image });

async function prepare(page, phoneHandler) {
    await page.addInitScript((profile) => {
        localStorage.setItem("joross-auth-session-v1", JSON.stringify({
            accessToken: "qr-browser-test-token", user: profile, expiresAt: Date.now() + 3600000,
        }));
    }, user);
    await page.route("**/api/v1/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path === "/api/v1/system/phone-access") return phoneHandler(route);
        if (path === "/api/v1/auth/me") return route.fulfill({ json: user });
        if (path.includes("/weather")) return route.fulfill({ status: 503, json: { detail: "Weather unavailable in isolated QR tests." } });
        return route.fulfill({ json: [] });
    });
    await page.goto("/dashboard");
    await expect(page.getByRole("button", { name: "Show phone QR code" })).toBeVisible();
}

test("button sits left of This Month, displays the QR in a modal and restores keyboard focus", async ({ page }) => {
    let requests = 0;
    await prepare(page, (route) => {
        requests += 1;
        expect(route.request().headers().authorization).toBe("Bearer qr-browser-test-token");
        return route.fulfill({ json: { links: [link("http://192.168.50.8:3105")] } });
    });
    const trigger = page.getByRole("button", { name: "Show phone QR code" });
    const period = page.getByRole("combobox", { name: "Dashboard date period" });
    await expect(period).toHaveValue("month");
    const triggerBox = await trigger.boundingBox();
    const periodBox = await period.boundingBox();
    expect(triggerBox.x + triggerBox.width).toBeLessThan(periodBox.x);
    expect(requests).toBe(0);
    await trigger.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("img", { name: "QR code to open Joross Farm on your phone" })).toHaveAttribute("src", /^data:image\/png;base64,/);
    await expect(dialog.getByRole("link")).toHaveAttribute("href", "http://192.168.50.8:3105");
    await expect(dialog.getByText(/same Wi-Fi or LAN/)).toBeVisible();
    if (process.env.QR_QA_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.QR_QA_SCREENSHOT_DIR}/qr-desktop.png` });
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
    await trigger.click();
    await expect(dialog.getByRole("link")).toBeVisible();
    expect(requests).toBe(2);
    await dialog.getByRole("button", { name: "Close QR code" }).click();
    await expect(dialog).not.toBeVisible();
    await expect(period).toHaveValue("month");
});

test("connection selection and refresh show the current network", async ({ page }) => {
    let requests = 0;
    await prepare(page, (route) => route.fulfill({ json: { links: ++requests === 1
        ? [link("http://farm.example.ts.net:3105", "tailscale"), link("http://192.168.50.8:3105")]
        : [link("http://10.1.2.3:3105")] } }));
    await page.getByRole("button", { name: "Show phone QR code" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/Keep Tailscale connected/)).toBeVisible();
    await dialog.getByRole("combobox", { name: "Connection" }).selectOption("http://192.168.50.8:3105");
    await expect(dialog.getByRole("link")).toHaveAttribute("href", "http://192.168.50.8:3105");
    await dialog.getByRole("button", { name: "Refresh QR code" }).click();
    await expect(dialog.getByRole("link")).toHaveAttribute("href", "http://10.1.2.3:3105");
    await expect(dialog.getByRole("combobox")).toHaveCount(0);
});

test("no-network and API errors provide recovery without a stale QR", async ({ page }) => {
    let requests = 0;
    await prepare(page, (route) => {
        requests += 1;
        if (requests === 1) return route.fulfill({ status: 503, json: { detail: "Phone link temporarily unavailable." } });
        if (requests === 2) return route.fulfill({ json: { links: [], message: "No LAN address was found. Connect to Wi-Fi, then refresh." } });
        return route.fulfill({ json: { links: [link("http://192.168.50.8:3105")] } });
    });
    await page.getByRole("button", { name: "Show phone QR code" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("alert")).toHaveText("Phone link temporarily unavailable.");
    await expect(dialog.getByRole("img")).toHaveCount(0);
    await dialog.getByRole("button", { name: "Refresh QR code" }).click();
    await expect(dialog.getByRole("status")).toContainText("No LAN address");
    await dialog.getByRole("button", { name: "Refresh QR code" }).click();
    await expect(dialog.getByRole("link")).toBeVisible();
    await expect(dialog.getByRole("alert")).toHaveCount(0);
});

test("closing during loading cancels the request and reopening fetches fresh data", async ({ page }) => {
    let requests = 0;
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    await prepare(page, async (route) => {
        if (++requests === 1) await held;
        await route.fulfill({ json: { links: [link("http://192.168.50.8:3105")] } }).catch(() => {});
    });
    const trigger = page.getByRole("button", { name: "Show phone QR code" });
    try {
        await trigger.click();
        await expect(page.getByRole("status").filter({ hasText: "Loading the current phone link" })).toBeVisible();
        await expect.poll(() => requests).toBe(1);
        await page.keyboard.press("Escape");
        await trigger.click();
        await expect(page.getByRole("dialog").getByRole("link")).toBeVisible();
        expect(requests).toBe(2);
    } finally {
        release();
    }
});

test.describe("mobile", () => {
    test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

    test("dark-mode dialog fits, traps focus and closes from the backdrop", async ({ page }) => {
    await prepare(page, (route) => route.fulfill({ json: { links: [link("http://192.168.50.8:3105")] } }));
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    await page.getByRole("button", { name: "Show phone QR code" }).tap({ timeout: 5000 });
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("link")).toBeVisible();
    const box = await dialog.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(box.height).toBeLessThanOrEqual(844);
    if (process.env.QR_QA_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.QR_QA_SCREENSHOT_DIR}/qr-mobile.png` });
    for (let i = 0; i < 7; i += 1) {
        await page.keyboard.press("Tab");
        expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    }
    await page.touchscreen.tap(2, 2);
    await expect(dialog).not.toBeVisible();
});

});
