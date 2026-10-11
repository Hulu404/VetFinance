import { defineConfig } from '@playwright/test';

// VF_WEB_URL, VF_E2E_EMAIL, VF_E2E_PASSWORD come from the environment; tests skip without them.
export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts/,
  timeout: 30_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.VF_WEB_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'desktop-1280', use: { browserName: 'chromium', viewport: { width: 1280, height: 800 } } },
    { name: 'tablet-820', use: { browserName: 'chromium', viewport: { width: 820, height: 1180 } } },
    { name: 'mobile-390', use: { browserName: 'chromium', viewport: { width: 390, height: 844 } } },
  ],
});
