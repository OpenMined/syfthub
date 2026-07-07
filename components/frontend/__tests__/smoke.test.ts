import { expect, test } from '@playwright/test';

import config from '../_config';
import { HomePage } from './pages/home.page';

test.describe('Smoke tests', () => {
  test('page loads with correct title', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(config.metadata.title);
  });

  test('sidebar navigation renders', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();

    await expect(home.sidebar).toBeVisible();
    await expect(home.browseLink).toBeVisible();
    await expect(home.buildLink).toBeVisible();
    await expect(home.aboutLink).toBeVisible();
  });

  test('heading is visible on home page', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();

    await expect(home.heading).toBeVisible();
  });

  test('theme toggle switches to dark mode', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();

    const html = page.locator('html');

    // Open theme dropdown and select Dark
    await home.themeToggle.click();
    await page.getByRole('menuitem', { name: /dark/i }).click();

    await expect(html).toHaveClass(/dark/);

    // Toggle back to Light
    await home.themeToggle.click();
    await page.getByRole('menuitem', { name: /light/i }).click();

    await expect(html).not.toHaveClass(/dark/);
  });
});
