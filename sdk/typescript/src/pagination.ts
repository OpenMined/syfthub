/**
 * Function type for fetching a page of items.
 */
export type PageFetcher<T> = (skip: number, limit: number) => Promise<T[]>;

/**
 * Lazy async iterator for paginated API responses.
 *
 * Fetches pages on demand as you iterate, minimizing API calls
 * and memory usage for large datasets.
 *
 * @example
 * // Iterate through all items
 * for await (const endpoint of client.hub.browse()) {
 *   console.log(endpoint.name);
 * }
 *
 * @example
 * // Get just the first page
 * const firstPage = await client.hub.browse().firstPage();
 *
 * @example
 * // Get first 10 items
 * const top10 = await client.hub.browse().take(10);
 */
export class PageIterator<T> implements AsyncIterable<T> {
  private items: T[] = [];
  private index = 0;
  private skip = 0;
  private exhausted = false;
  private initialized = false;

  /**
   * Create a new PageIterator.
   *
   * @param fetcher - Function that fetches a page of items given skip and limit
   * @param pageSize - Number of items to fetch per page (default: 20)
   */
  constructor(
    private readonly fetcher: PageFetcher<T>,
    private readonly pageSize: number = 20
  ) {}

  /**
   * Async iterator implementation for `for await...of` loops.
   */
  async *[Symbol.asyncIterator](): AsyncIterator<T> {
    while (true) {
      // If we've consumed all items in the current page
      if (this.index >= this.items.length) {
        if (this.exhausted) break;
        await this.fetchNextPage();
        if (this.items.length === 0) break;
      }

      const item = this.items[this.index];
      if (item === undefined) break;

      this.index++;
      yield item;
    }
  }

  /**
   * Get just the first page of results.
   *
   * @returns Promise resolving to the first page of items
   */
  async firstPage(): Promise<T[]> {
    if (!this.initialized) {
      await this.fetchNextPage();
    }
    return [...this.items];
  }

  /**
   * Get all items across all pages.
   *
   * Warning: This loads all items into memory. For large datasets,
   * consider iterating with `for await...of` instead.
   *
   * @returns Promise resolving to all items
   */
  async all(): Promise<T[]> {
    const results: T[] = [];
    for await (const item of this) {
      results.push(item);
    }
    return results;
  }

  /**
   * Get the first N items.
   *
   * @param n - Maximum number of items to return
   * @returns Promise resolving to up to N items
   */
  async take(n: number): Promise<T[]> {
    const results: T[] = [];
    for await (const item of this) {
      results.push(item);
      if (results.length >= n) break;
    }
    return results;
  }

  /**
   * Fetch the next page of items from the API.
   */
  private async fetchNextPage(): Promise<void> {
    const page = await this.fetcher(this.skip, this.pageSize);
    this.items = page;
    this.index = 0;
    this.skip += this.pageSize;
    this.exhausted = page.length < this.pageSize;
    this.initialized = true;
  }
}
