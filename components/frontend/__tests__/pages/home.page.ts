import type { Locator, Page } from '@playwright/test';

export class HomePage {
  readonly page: Page;
  readonly heading: Locator;
  readonly sidebar: Locator;
  readonly themeToggle: Locator;
  readonly chatLink: Locator;
  readonly browseLink: Locator;
  readonly buildLink: Locator;
  readonly aboutLink: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.locator('h1').first();
    this.sidebar = page.locator('nav').first();
    this.themeToggle = page.getByRole('button', { name: /toggle theme/i });
    this.chatLink = page.getByRole('link', { name: /chat/i });
    this.browseLink = page.getByRole('link', { name: /browse/i });
    this.buildLink = page.getByRole('link', { name: /build/i });
    this.aboutLink = page.getByRole('link', { name: /about/i });
  }

  async goto() {
    await this.page.goto('/');
  }
}
