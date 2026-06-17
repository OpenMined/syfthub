/**
 * Search resource for retrieval-only queries via the Aggregator service.
 *
 * Symmetric counterpart to {@link ChatResource}: where `client.chat.complete()`
 * retrieves context *and* generates a model response, `client.search.query()`
 * retrieves documents from data sources without invoking any model.
 *
 * @example
 * // Symmetric to client.chat.complete(...)
 * const result = await client.search.query({
 *   prompt: 'What happened at EPFL this week?',
 *   dataSources: ['epfl-news/epfl-news'],
 * });
 * for (const doc of result.documents) {
 *   console.log(doc.title, '->', doc.content.slice(0, 80));
 * }
 *
 * Authentication and billing are handled by the aggregator exactly as for chat:
 * satellite tokens are minted per data source owner, and metered endpoints that
 * respond with `402 Payment Required` are settled via the user's Hub wallet.
 */

import type { SearchQueryOptions, SearchResponse } from '../models/chat.js';
import type { ChatResource } from './chat.js';

/**
 * Retrieval-only search via the Aggregator.
 *
 * Thin facade over {@link ChatResource.retrieve}, exposed as `client.search` to
 * mirror the shape of `client.chat`.
 */
export class SearchResource {
  /**
   * @param chat - The chat resource that owns aggregator communication and
   *   request preparation (satellite tokens, MPP, collective expansion). Search
   *   reuses it rather than duplicating that logic.
   */
  constructor(private readonly chat: ChatResource) {}

  /**
   * Retrieve documents from data sources without model generation.
   *
   * @param options - Search options (prompt, data sources, top-k, etc.)
   * @returns SearchResponse with retrieved documents and per-source metadata
   *
   * @example
   * const result = await client.search.query({
   *   prompt: 'Hello, world!',
   *   dataSources: ['epfl-news/epfl-news'],
   * });
   * console.log(result.documents.length, 'documents');
   */
  async query(options: SearchQueryOptions): Promise<SearchResponse> {
    return this.chat.retrieve(options);
  }
}
