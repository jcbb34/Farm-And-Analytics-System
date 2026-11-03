import { defineConfig } from "@playwright/test";

export default defineConfig({
    testDir: "./browser-tests",
    fullyParallel: false,
    workers: 1,
    reporter: "list",
    use: {
        baseURL: "http://127.0.0.1:3100",
        viewport: { width: 1440, height: 1000 },
        browserName: "chromium",
        serviceWorkers: "block",
        launchOptions: {
            ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
                ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
                : {}),
        },
    },
    webServer: {
        command: "npm run start -- -H 127.0.0.1 -p 3100",
        url: "http://127.0.0.1:3100/login",
        reuseExistingServer: !process.env.CI,
        timeout: 60000,
    },
});
