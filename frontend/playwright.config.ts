import { defineConfig } from "@playwright/test";

const chromePath = process.env.CINEGRAPH_CHROME_PATH;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  use: {
    baseURL: "http://localhost:3102",
    browserName: "chromium",
    launchOptions: chromePath ? { executablePath: chromePath } : undefined,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --port 3102",
    url: "http://localhost:3102",
    reuseExistingServer: false,
    timeout: 30_000,
    env: { API_INTERNAL_URL: "http://127.0.0.1:18001/api/v1" },
  },
});
