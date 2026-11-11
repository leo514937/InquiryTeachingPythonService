import { defineConfig } from '@playwright/test';

const backendPort = process.env.INQUIRY_E2E_PORT || '18760';
const webPort = process.env.INQUIRY_E2E_WEB_PORT || '15730';

export default defineConfig({
  testDir: './tests/workspace-e2e',
  outputDir: process.env.INQUIRY_E2E_OUTPUT_DIR || 'test-results',
  timeout: 60000,
  workers: 1,
  use: { baseURL: `http://127.0.0.1:${webPort}`, browserName: 'chromium', launchOptions: { executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe' } },
  webServer: [
    { command: 'python ../tests/workspace_e2e_server.py', url: `http://127.0.0.1:${backendPort}/health`, timeout: 30000, reuseExistingServer: false },
    { command: `npm run dev -- --host 127.0.0.1 --port ${webPort} --strictPort`, url: `http://127.0.0.1:${webPort}`, timeout: 30000, reuseExistingServer: false, env: { VITE_API_BASE: `http://127.0.0.1:${backendPort}` } },
  ],
});
