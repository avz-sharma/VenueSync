/**
 * VenueSync — E2E Smoke Test
 *
 * Playwright end-to-end smoke test that verifies the critical user flow:
 * 1. Navigate to the local frontend URL.
 * 2. Click the "Load Demo Scenario" button.
 * 3. Verify the Reasoning Trace Panel becomes visible in the DOM.
 *
 * Prerequisites:
 *   - Backend running: uvicorn backend.main:app --port 8000
 *   - Frontend running: npm run dev (Vite on port 5173)
 *
 * Run with:
 *   npx playwright test tests/e2e/smoke.spec.ts
 */

import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:5173';

test.describe('VenueSync — Smoke Test', () => {
  test('Load Demo Scenario reveals Reasoning Trace Panel', async ({ page }) => {
    // 1. Navigate to the dashboard
    await page.goto(BASE_URL);

    // Verify the page loaded by checking for the main heading
    await expect(page.locator('h1')).toContainText('VenueSync');

    // 2. Click the "Load Demo Scenario" button
    const loadDemoButton = page.getByRole('button', { name: /Load Demo Scenario/i });
    await expect(loadDemoButton).toBeVisible();
    await loadDemoButton.click();

    // 3. Wait for the Reasoning Trace Panel to appear
    //    The ReasoningTracePanel renders with "AI Judgment Trace" header text
    //    and the RecommendationQueue renders "AI Recommendation Queue"
    const reasoningTracePanel = page.locator('text=AI Judgment Trace').first();
    await expect(reasoningTracePanel).toBeVisible({ timeout: 30_000 });

    // Additionally verify the recommendation queue is showing action cards
    const recommendationQueue = page.locator('text=AI Logic Queue');
    await expect(recommendationQueue).toBeVisible({ timeout: 10_000 });
  });
});
