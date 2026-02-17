import type { Locator, Page } from '@playwright/test';

export class ChatPage {
  readonly page: Page;
  readonly queryInput: Locator;
  readonly heading: Locator;

  constructor(page: Page) {
    this.page = page;
    this.queryInput = page.getByPlaceholder(/ask/i);
    this.heading = page.locator('h1').first();
  }

  async goto() {
    await this.page.goto('/chat');
  }
}
