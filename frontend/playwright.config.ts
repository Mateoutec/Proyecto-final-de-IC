import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const PORT = 8766;
const FAKE_ARGS = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"];
// Video con un rostro de la imagen de ejemplo 't1' (lo genera scripts/e2e_server.py al arrancar).
const FACE_VIDEO = fileURLToPath(new URL("./e2e/fixtures/rostro.y4m", import.meta.url));

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    locale: "es-PE",
    timezoneId: "America/Lima",
    acceptDownloads: true,
    permissions: ["camera"],
  },
  projects: [
    {
      name: "chromium",
      testIgnore: /rostro\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, launchOptions: { args: FAKE_ARGS } },
    },
    {
      name: "chromium-rostro",
      testMatch: /rostro\.spec\.ts/,
      dependencies: ["chromium"],
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        launchOptions: { args: [...FAKE_ARGS, `--use-file-for-fake-video-capture=${FACE_VIDEO}`] },
      },
    },
  ],
  webServer: {
    command: "uv run python scripts/e2e_server.py",
    cwd: "../backend",
    url: `http://127.0.0.1:${PORT}/api/health`,
    timeout: 120_000,
    reuseExistingServer: false,
  },
});
