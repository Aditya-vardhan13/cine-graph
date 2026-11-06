import { defineConfig } from "@playwright/test";

const chromePath = process.env.CINEGRAPH_CHROME_PATH;
const testPort = process.env.CINEGRAPH_E2E_PORT ?? "3102";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  use: {
    baseURL: `http://localhost:${testPort}`,
    browserName: "chromium",
    launchOptions: chromePath ? { executablePath: chromePath } : undefined,
    trace: "retain-on-failure",
  },
  webServer: {
    command: `npm run dev -- --port ${testPort}`,
    url: `http://localhost:${testPort}`,
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      API_INTERNAL_URL: process.env.CINEGRAPH_E2E_API_URL ?? "http://127.0.0.1:18001/api/v1",
      CINEGRAPH_LOCAL_ADMIN_MODE: "1",
      CINEGRAPH_BIND_ADDRESS: "127.0.0.1",
      CINEGRAPH_ADMIN_EMAIL: "adityavk1310@gmail.com",
      CINEGRAPH_NEXT_DIST_DIR: ".next-playwright",
    },
  },
});
