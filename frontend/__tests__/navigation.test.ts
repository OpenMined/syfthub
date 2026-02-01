import { expect, test } from '@playwright/test';

import { HomePage } from './pages/home.page';

test.describe('Navigation', () => {
  test('navigates to browse page', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();

    await home.browseLink.click();
    await expect(page).toHaveURL(/\/browse/);
  });

  test('navigates to build page', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();

    await home.buildLink.click();
    await expect(page).toHaveURL(/\/build/);
  });

  test('navigates to about page', async ({ page }) => {
    const home = new HomePage(page);
    await home.goto();

    await home.aboutLink.click();
    await expect(page).toHaveURL(/\/about/);
  });

  test('unknown route shows 404 page', async ({ page }) => {
    await page.goto('/this-route-does-not-exist-xyz');

    // Should see the 404 heading
    await expect(page.getByRole('heading', { name: '404' })).toBeVisible();
  });
});
