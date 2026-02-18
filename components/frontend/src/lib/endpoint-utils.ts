/**
 * Endpoint Utilities - Connects to SyftHub backend via SDK
 *
 * This module provides:
 * - Functions for fetching and managing endpoints
 * - Type mappings between SDK types and frontend types
 * - Utility functions for ChatSource transformation
 */
import type { Endpoint as SdkEndpoint, EndpointPublic as SdkEndpointPublic } from './sdk-client';
import type {
  ChatSource,
  EndpointCreate,
  EndpointFilters,
  EndpointResponse,
  EndpointType,
  EndpointUpdate,
  PaginationParams
} from './types';

import { syftClient } from './sdk-client';

// ============================================================================
// Type Matching Helpers
// ============================================================================

/**
 * Check if an endpoint type should be treated as a model.
 * model_data_source endpoints are included.
 */
export function isModelEndpoint(type: EndpointType): boolean {
  return type === 'model' || type === 'model_data_source';
}

/**
 * Check if an endpoint type should be treated as a data source.
 * model_data_source endpoints are included.
 */
export function isDataSourceEndpoint(type: EndpointType): boolean {
  return type === 'data_source' || type === 'model_data_source';
}

// ============================================================================
// Type Mapping Utilities
// ============================================================================

/**
 * Format a relative time string from a date.
 */
function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffInHours = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60));

  if (diffInHours < 1) return 'just now';
  if (diffInHours < 24) return `${String(diffInHours)} hour${diffInHours === 1 ? '' : 's'} ago`;

  const diffInDays = Math.floor(diffInHours / 24);
  if (diffInDays < 7) return `${String(diffInDays)} day${diffInDays === 1 ? '' : 's'} ago`;

  const diffInWeeks = Math.floor(diffInDays / 7);
  if (diffInDays < 30) return `${String(diffInWeeks)} week${diffInWeeks === 1 ? '' : 's'} ago`;

  const diffInMonths = Math.floor(diffInDays / 30);
  return `${String(diffInMonths)} month${diffInMonths === 1 ? '' : 's'} ago`;
}

/**
 * Convert SDK EndpointPublic to frontend ChatSource.
 *
 * This transforms the API response into a UI-friendly format with:
 * - Relative time formatting
 * - Status derivation based on update time
 * - Tags from backend
 * - URL extraction from connect config
 */
export function mapEndpointPublicToSource(endpoint: SdkEndpointPublic): ChatSource {
  // Get tags directly from backend (or empty array if not set)
  // Use 'in' check since tags may not be present on all endpoint objects
  const tags =
    'tags' in endpoint && Array.isArray(endpoint.tags) ? [...(endpoint.tags as string[])] : [];

  // Get policies for mapping
  const policies = endpoint.policies;

  // Determine status based on updated time
  const updatedDate = endpoint.updatedAt;
  const daysSinceUpdate = Math.floor((Date.now() - updatedDate.getTime()) / (1000 * 60 * 60 * 24));

  let status: 'active' | 'warning' | 'inactive' = 'active';
  if (daysSinceUpdate > 7) status = 'warning';
  if (daysSinceUpdate > 30) status = 'inactive';

  const ownerUsername = endpoint.ownerUsername;
  const fullPath = `${ownerUsername}/${endpoint.slug}`;

  // Extract URL and tenant_name from first enabled connection (if available)
  const connections = endpoint.connect;
  const enabledConnection = connections.find((c) => c.enabled);
  const url =
    enabledConnection?.config && typeof enabledConnection.config.url === 'string'
      ? enabledConnection.config.url
      : undefined;
  const tenantName =
    enabledConnection?.config && typeof enabledConnection.config.tenant_name === 'string'
      ? enabledConnection.config.tenant_name
      : undefined;

  // Map SDK connections to frontend Connection type
  const mappedConnections = connections.map((c) => ({
    type: c.type,
    enabled: c.enabled,
    description: c.description,
    config: { ...c.config }
  }));

  // Map SDK policies to frontend Policy type
  const mappedPolicies = policies.map((p) => ({
    type: p.type,
    version: p.version,
    enabled: p.enabled,
    description: p.description,
    config: { ...p.config }
  }));

  return {
    id: endpoint.slug,
    name: endpoint.name,
    tags: tags,
    description: endpoint.description,
    type: endpoint.type,
    updated: formatRelativeTime(updatedDate),
    status: status,
    slug: endpoint.slug,
    stars_count: endpoint.starsCount,
    version: endpoint.version,
    readme: endpoint.readme,
    contributors_count: endpoint.contributorsCount,
    owner_username: ownerUsername,
    full_path: fullPath,
    url: url,
    tenant_name: tenantName,
    connections: mappedConnections,
    policies: mappedPolicies
  };
}

/**
 * Convert SDK Endpoint to frontend EndpointResponse.
 *
 * @param endpoint - SDK Endpoint object
 * @param ownerUsername - Optional owner username (for constructing full_path)
 */
export function mapSdkEndpointToResponse(
  endpoint: SdkEndpoint,
  ownerUsername?: string
): EndpointResponse {
  return {
    id: endpoint.id,
    user_id: endpoint.userId ?? undefined,
    organization_id: endpoint.organizationId ?? undefined,
    name: endpoint.name,
    slug: endpoint.slug,
    description: endpoint.description,
    type: endpoint.type,
    visibility: endpoint.visibility,
    is_active: endpoint.isActive,
    contributors: [...endpoint.contributors],
    version: endpoint.version,
    readme: endpoint.readme,
    stars_count: endpoint.starsCount,
    policies: endpoint.policies.map((p) => ({ ...p })),
    connect: endpoint.connect.map((c) => ({ ...c })),
    created_at: endpoint.createdAt.toISOString(),
    updated_at: endpoint.updatedAt.toISOString(),
    // Add owner_username if provided (useful for constructing paths)
    ...(ownerUsername ? { owner_username: ownerUsername } : {})
  } as EndpointResponse;
}

// ============================================================================
// Public Endpoint Functions (No Auth Required)
// ============================================================================

/**
 * Response type for paginated endpoint queries.
 */
export interface PaginatedEndpointsResponse {
  items: ChatSource[];
  hasNextPage: boolean;
}

/**
 * Raw API response shape for public endpoints (snake_case from backend).
 * The SDK normally transforms these to camelCase, but getPublicEndpointsPaginated
 * uses raw fetch() to support server-side pagination, so we transform manually.
 */
interface RawEndpointPublic {
  name: string;
  slug: string;
  description: string;
  type: string;
  owner_username: string;
  contributors_count: number;
  version: string;
  readme: string;
  tags: string[];
  stars_count: number;
  policies: Array<{
    type: string;
    version: string;
    enabled: boolean;
    description: string;
    config: Record<string, unknown>;
  }>;
  connect: Array<{
    type: string;
    enabled: boolean;
    description: string;
    config: Record<string, unknown>;
  }>;
  created_at: string;
  updated_at: string;
}

/**
 * Transform a raw API endpoint response (snake_case) to the SDK EndpointPublic
 * format (camelCase with Date objects) that mapEndpointPublicToSource expects.
 */
function transformRawEndpoint(raw: RawEndpointPublic): SdkEndpointPublic {
  return {
    name: raw.name,
    slug: raw.slug,
    description: raw.description,
    type: raw.type,
    ownerUsername: raw.owner_username,
    contributorsCount: raw.contributors_count,
    version: raw.version,
    readme: raw.readme,
    tags: raw.tags,
    starsCount: raw.stars_count,
    policies: raw.policies,
    connect: raw.connect,
    createdAt: new Date(raw.created_at),
    updatedAt: new Date(raw.updated_at)
  } as unknown as SdkEndpointPublic;
}

/**
 * Get public endpoints from the hub with pagination support.
 *
 * Uses the "fetch N+1" pattern to detect if there are more pages.
 * Uses raw fetch() instead of the SDK client to support server-side
 * pagination with skip/limit and endpoint_type filtering.
 *
 * @param params - Pagination and filter parameters
 * @returns Paginated response with items and hasNextPage flag
 */
export async function getPublicEndpointsPaginated(
  params: { page?: number; limit?: number; endpoint_type?: EndpointType } = {}
): Promise<PaginatedEndpointsResponse> {
  const { page = 1, limit = 12, endpoint_type } = params;
  const skip = (page - 1) * limit;

  try {
    // Build query params
    const queryParams = new URLSearchParams({
      skip: String(skip),
      limit: String(limit + 1) // Fetch one extra to detect if there's a next page
    });

    if (endpoint_type) {
      queryParams.append('endpoint_type', endpoint_type);
    }

    const response = await fetch(`/api/v1/endpoints/public?${queryParams.toString()}`);

    if (!response.ok) {
      throw new Error(`Failed to fetch endpoints: ${response.statusText}`);
    }

    // Raw API returns snake_case JSON; transform to camelCase SDK types
    const rawData = (await response.json()) as RawEndpointPublic[];
    const data = rawData.map((ep) => transformRawEndpoint(ep));

    // Check if there's a next page (we fetched limit+1 items)
    const hasNextPage = data.length > limit;

    // Map only the requested number of items
    const items = data.slice(0, limit).map((ep) => mapEndpointPublicToSource(ep));

    return { items, hasNextPage };
  } catch (error) {
    console.error('Failed to fetch paginated public endpoints:', error);
    return { items: [], hasNextPage: false };
  }
}

/**
 * Get public endpoints from the hub.
 *
 * Uses server-side filtering by endpoint_type to ensure correct results
 * even when one type dominates the endpoint list (e.g., many data sources).
 *
 * @param params - Pagination and filter parameters
 * @returns Array of ChatSource objects
 */
export async function getPublicEndpoints(
  params: PaginationParams & { endpoint_type?: EndpointType } = {}
): Promise<ChatSource[]> {
  const { limit = 10, endpoint_type } = params;

  try {
    // Use server-side filtering via SDK to get correct results
    const endpoints = await syftClient.hub
      .browse({ pageSize: limit, endpointType: endpoint_type })
      .firstPage();

    return endpoints.map((ep) => mapEndpointPublicToSource(ep));
  } catch (error) {
    console.error('Failed to fetch public endpoints:', error);
    return [];
  }
}

/**
 * Get trending endpoints sorted by stars.
 *
 * Uses server-side filtering by endpoint_type to ensure correct results
 * even when one type dominates the endpoint list (e.g., many data sources).
 *
 * @param params - Pagination and filter parameters
 * @returns Array of ChatSource objects
 */
export async function getTrendingEndpoints(
  params: PaginationParams & { min_stars?: number; endpoint_type?: EndpointType } = {}
): Promise<ChatSource[]> {
  const { limit = 10, min_stars, endpoint_type } = params;

  try {
    // Use server-side filtering via SDK to get correct results
    const endpoints = await syftClient.hub
      .trending({ minStars: min_stars, pageSize: limit, endpointType: endpoint_type })
      .firstPage();

    return endpoints.map((ep) => mapEndpointPublicToSource(ep));
  } catch (error) {
    console.error('Failed to fetch trending endpoints:', error);
    return [];
  }
}

/**
 * Get the total count of all public endpoints.
 *
 * @returns The total number of public endpoints
 */
export async function getTotalEndpointsCount(): Promise<number> {
  try {
    const endpoints = await syftClient.hub.browse().all();
    return endpoints.length;
  } catch (error) {
    console.error('Failed to fetch total endpoints count:', error);
    return 0;
  }
}

// ============================================================================
// Guest-Accessible Endpoint Functions (No Auth Required)
// ============================================================================

/**
 * Get guest-accessible endpoints (public, active, no policies).
 *
 * @param params - Pagination and filter parameters
 * @returns Array of ChatSource objects
 */
export async function getGuestAccessibleEndpoints(
  params: PaginationParams & { endpoint_type?: EndpointType } = {}
): Promise<ChatSource[]> {
  const { limit = 10 } = params;

  try {
    const endpoints = await syftClient.hub
      .guestAccessible({ pageSize: limit, endpointType: params.endpoint_type })
      .firstPage();

    return endpoints.map((ep) => mapEndpointPublicToSource(ep));
  } catch (error) {
    console.error('Failed to fetch guest-accessible endpoints:', error);
    return [];
  }
}

/**
 * Get guest-accessible model endpoints for chat.
 *
 * @param limit - Maximum number of results
 * @returns Array of ChatSource objects for models
 */
export async function getGuestAccessibleModels(limit = 20): Promise<ChatSource[]> {
  return getGuestAccessibleEndpoints({ limit, endpoint_type: 'model' });
}

/**
 * Get guest-accessible data source endpoints for chat.
 *
 * @param limit - Maximum number of results
 * @returns Array of ChatSource objects for data sources
 */
export async function getGuestAccessibleDataSources(limit = 20): Promise<ChatSource[]> {
  return getGuestAccessibleEndpoints({ limit, endpoint_type: 'data_source' });
}

// ============================================================================
// User Endpoint Functions (Auth Required)
// ============================================================================

/**
 * Get the current user's endpoints.
 *
 * @param filters - Filter parameters
 * @param ownerUsername - Username of the current user (for path construction)
 * @returns Array of EndpointResponse objects
 */
export async function getUserEndpoints(
  filters: EndpointFilters = {},
  ownerUsername?: string
): Promise<EndpointResponse[]> {
  const { visibility } = filters;

  const endpoints = await syftClient.myEndpoints
    .list({
      visibility: visibility as 'public' | 'private' | 'internal' | undefined,
      pageSize: 100
    })
    .all();

  return endpoints.map((ep) => mapSdkEndpointToResponse(ep, ownerUsername));
}

/**
 * Get a specific endpoint by path.
 *
 * @param path - Endpoint path in "owner/slug" format
 * @returns EndpointResponse object
 */
export async function getEndpointByPath(path: string): Promise<EndpointResponse> {
  const endpoint = await syftClient.myEndpoints.get(path);
  const ownerUsername = path.split('/')[0];
  return mapSdkEndpointToResponse(endpoint, ownerUsername);
}

/**
 * Create a new endpoint.
 *
 * @param endpointData - Endpoint creation data
 * @param organizationId - Optional organization ID for org-owned endpoints
 * @param ownerUsername - Username of the owner (for response path)
 * @returns Created EndpointResponse
 */
export async function createEndpoint(
  endpointData: EndpointCreate,
  organizationId?: number,
  ownerUsername?: string
): Promise<EndpointResponse> {
  const endpoint = await syftClient.myEndpoints.create(
    {
      name: endpointData.name,
      type: endpointData.type,
      visibility: endpointData.visibility,
      description: endpointData.description,
      slug: endpointData.slug,
      version: endpointData.version,
      readme: endpointData.readme,
      policies: endpointData.policies,
      connect: endpointData.connect,
      contributors: endpointData.contributors
    },
    organizationId
  );

  return mapSdkEndpointToResponse(endpoint, ownerUsername);
}

/**
 * Update an endpoint by path.
 *
 * @param path - Endpoint path in "owner/slug" format
 * @param updateData - Fields to update
 * @returns Updated EndpointResponse
 */
export async function updateEndpointByPath(
  path: string,
  updateData: EndpointUpdate
): Promise<EndpointResponse> {
  const endpoint = await syftClient.myEndpoints.update(path, {
    name: updateData.name,
    description: updateData.description,
    visibility: updateData.visibility,
    version: updateData.version,
    readme: updateData.readme,
    policies: updateData.policies,
    connect: updateData.connect,
    contributors: updateData.contributors
  });

  const ownerUsername = path.split('/')[0];
  return mapSdkEndpointToResponse(endpoint, ownerUsername);
}

/**
 * Delete an endpoint by path.
 *
 * @param path - Endpoint path in "owner/slug" format
 */
export async function deleteEndpointByPath(path: string): Promise<void> {
  await syftClient.myEndpoints.delete(path);
}

// ============================================================================
// Chat Data Source Utilities
// ============================================================================

/**
 * Get data sources for chat (combines trending and public data_source endpoints).
 *
 * @param limit - Maximum number of results
 * @returns Array of ChatSource objects (deduplicated)
 */
export async function getChatDataSources(limit = 20): Promise<ChatSource[]> {
  try {
    const trendingLimit = Math.floor(limit / 2);
    const publicLimit = limit - trendingLimit;

    const [trending, publicEndpoints] = await Promise.all([
      getTrendingEndpoints({ limit: trendingLimit, endpoint_type: 'data_source' }),
      getPublicEndpoints({ limit: publicLimit, endpoint_type: 'data_source' })
    ]);

    // Combine and deduplicate by full_path (owner/slug) to correctly handle
    // models from different owners with the same slug
    const combinedSources: ChatSource[] = [];
    const seenPaths = new Set<string>();

    // Add trending first (higher priority)
    for (const source of trending) {
      const path = source.full_path ?? `${source.owner_username ?? 'unknown'}/${source.slug}`;
      if (!seenPaths.has(path)) {
        seenPaths.add(path);
        combinedSources.push(source);
      }
    }

    // Add public endpoints that aren't already included
    for (const source of publicEndpoints) {
      const path = source.full_path ?? `${source.owner_username ?? 'unknown'}/${source.slug}`;
      if (!seenPaths.has(path)) {
        seenPaths.add(path);
        combinedSources.push(source);
      }
    }

    return combinedSources;
  } catch (error) {
    console.error('Failed to fetch chat data sources:', error);
    return [];
  }
}

/**
 * Get model endpoints for chat (combines trending and public model endpoints).
 *
 * @param limit - Maximum number of results
 * @returns Array of ChatSource objects (deduplicated)
 */
export async function getChatModels(limit = 20): Promise<ChatSource[]> {
  try {
    const trendingLimit = Math.floor(limit / 2);
    const publicLimit = limit - trendingLimit;

    const [trending, publicEndpoints] = await Promise.all([
      getTrendingEndpoints({ limit: trendingLimit, endpoint_type: 'model' }),
      getPublicEndpoints({ limit: publicLimit, endpoint_type: 'model' })
    ]);

    // Combine and deduplicate by full_path (owner/slug) to correctly handle
    // models from different owners with the same slug
    const combinedModels: ChatSource[] = [];
    const seenPaths = new Set<string>();

    // Add trending first (higher priority)
    for (const model of trending) {
      const path = model.full_path ?? `${model.owner_username ?? 'unknown'}/${model.slug}`;
      if (!seenPaths.has(path)) {
        seenPaths.add(path);
        combinedModels.push(model);
      }
    }

    // Add public endpoints that aren't already included
    for (const model of publicEndpoints) {
      const path = model.full_path ?? `${model.owner_username ?? 'unknown'}/${model.slug}`;
      if (!seenPaths.has(path)) {
        seenPaths.add(path);
        combinedModels.push(model);
      }
    }

    return combinedModels;
  } catch (error) {
    console.error('Failed to fetch chat models:', error);
    return [];
  }
}

// ============================================================================
// Query Relevance Utilities
// ============================================================================

/**
 * Extract endpoint path mentions from a query string.
 * Looks for patterns like "owner/endpoint-name" in the text.
 *
 * @param query - The user's query string
 * @returns Array of potential endpoint paths found
 */
export function parseEndpointMentions(query: string): string[] {
  // Match patterns like "owner/endpoint-name" or "owner/endpoint_name"
  // Supports alphanumeric, hyphens, and underscores
  const pathPattern = /\b([a-zA-Z][\w-]*\/[\w-]+)\b/g;
  const matches = query.match(pathPattern);
  return matches ?? [];
}

/**
 * Find an endpoint by exact path match from available sources.
 *
 * @param sources - Available chat sources
 * @param path - Endpoint path to find (owner/slug format)
 * @returns The matching ChatSource or undefined
 */
export function findEndpointByPath(sources: ChatSource[], path: string): ChatSource | undefined {
  const normalizedPath = path.toLowerCase();
  return sources.find((source) => source.full_path?.toLowerCase() === normalizedPath);
}

/**
 * Find an endpoint by name match from available sources.
 *
 * @param sources - Available chat sources
 * @param name - Endpoint name to find (case-insensitive)
 * @returns The matching ChatSource or undefined
 */
export function findEndpointByName(sources: ChatSource[], name: string): ChatSource | undefined {
  const normalizedName = name.toLowerCase().trim();
  return sources.find((source) => source.name.toLowerCase() === normalizedName);
}

/**
 * Calculate a relevance score for a source based on query keywords.
 * Higher score = more relevant.
 *
 * @param source - The chat source to score
 * @param keywords - Array of keywords to match against
 * @returns Relevance score (0 = no match)
 */
function calculateRelevanceScore(source: ChatSource, keywords: string[]): number {
  let score = 0;
  const nameWords = source.name.toLowerCase().split(/[\s-_]+/);
  const descText = source.description.toLowerCase();
  const tags = source.tags.map((t) => t.toLowerCase());
  const readmeText = source.readme.toLowerCase();

  for (const keyword of keywords) {
    // Exact name word match (highest weight)
    if (nameWords.includes(keyword)) {
      score += 10;
    }
    // Name contains keyword
    else if (source.name.toLowerCase().includes(keyword)) {
      score += 5;
    }

    // Description contains keyword (high weight)
    if (descText.includes(keyword)) {
      score += 8;
    }

    // Tag exact match
    if (tags.includes(keyword)) {
      score += 4;
    }
    // Tag contains keyword
    else if (tags.some((tag) => tag.includes(keyword))) {
      score += 2;
    }

    // Readme/summary contains keyword (lower weight, can be lengthy)
    if (readmeText.includes(keyword)) {
      score += 1;
    }
  }

  return score;
}

/**
 * Extract meaningful keywords from a query string.
 * Filters out common stop words and short words.
 *
 * @param query - The user's query string
 * @returns Array of meaningful keywords
 */
function extractKeywords(query: string): string[] {
  const stopWords = new Set([
    'a',
    'an',
    'the',
    'is',
    'are',
    'was',
    'were',
    'be',
    'been',
    'being',
    'have',
    'has',
    'had',
    'do',
    'does',
    'did',
    'will',
    'would',
    'could',
    'should',
    'may',
    'might',
    'must',
    'shall',
    'can',
    'of',
    'at',
    'by',
    'for',
    'with',
    'about',
    'against',
    'between',
    'into',
    'through',
    'during',
    'before',
    'after',
    'above',
    'below',
    'to',
    'from',
    'up',
    'down',
    'in',
    'out',
    'on',
    'off',
    'over',
    'under',
    'again',
    'further',
    'then',
    'once',
    'and',
    'but',
    'or',
    'nor',
    'so',
    'yet',
    'both',
    'each',
    'few',
    'more',
    'most',
    'other',
    'some',
    'such',
    'no',
    'not',
    'only',
    'own',
    'same',
    'than',
    'too',
    'very',
    'just',
    'also',
    'now',
    'here',
    'there',
    'when',
    'where',
    'why',
    'how',
    'all',
    'any',
    'what',
    'which',
    'who',
    'whom',
    'this',
    'that',
    'these',
    'those',
    'am',
    'i',
    'me',
    'my',
    'myself',
    'we',
    'our',
    'ours',
    'you',
    'your',
    'yours',
    'he',
    'him',
    'his',
    'she',
    'her',
    'hers',
    'it',
    'its',
    'they',
    'them',
    'their',
    'tell',
    'show',
    'give',
    'get',
    'find',
    'use',
    'using',
    'want',
    'need',
    'like',
    'know',
    'think',
    'make',
    'help',
    'please'
  ]);

  // Split on whitespace and punctuation, filter meaningful words
  const words = query
    .toLowerCase()
    .split(/[\s,.:;!?()[\]{}'"]+/)
    .filter((word) => word.length >= 2 && !stopWords.has(word));

  return [...new Set(words)]; // Deduplicate
}

/**
 * Filter sources by relevance to a query.
 * Returns sources sorted by relevance score (highest first).
 *
 * @param sources - All available chat sources
 * @param query - The user's query string
 * @param minScore - Minimum score to include (default: 1)
 * @returns Filtered and sorted array of relevant sources
 */
export function filterRelevantSources(
  sources: ChatSource[],
  query: string,
  minScore = 1
): ChatSource[] {
  const keywords = extractKeywords(query);

  if (keywords.length === 0) {
    // No meaningful keywords, return all sources
    return sources;
  }

  // Score and filter sources
  const scoredSources = sources
    .map((source) => ({
      source,
      score: calculateRelevanceScore(source, keywords)
    }))
    .filter(({ score }) => score >= minScore)
    .toSorted((a, b) => b.score - a.score);

  return scoredSources.map(({ source }) => source);
}

/**
 * Try to find an endpoint by name from words in the query.
 * Checks single words and adjacent word pairs.
 */
function findEndpointByQueryWords(
  query: string,
  availableSources: ChatSource[]
): ChatSource | undefined {
  const words = query.split(/\s+/);

  for (let index = 0; index < words.length; index++) {
    const singleWord = words[index];
    if (singleWord) {
      const matched = findEndpointByName(availableSources, singleWord);
      if (matched) return matched;
    }

    // Try word pairs (e.g., "Financial Data")
    const nextWord = words[index + 1];
    if (singleWord && nextWord) {
      const matched = findEndpointByName(availableSources, `${singleWord} ${nextWord}`);
      if (matched) return matched;
    }
  }

  return undefined;
}

/**
 * Analyze a query to determine the best action for source selection.
 *
 * @param query - The user's query string
 * @param availableSources - All available chat sources
 * @returns Analysis result with recommended action
 */
export function analyzeQueryForSources(
  query: string,
  availableSources: ChatSource[]
): {
  action: 'auto-select' | 'show-relevant' | 'show-all';
  matchedEndpoint?: ChatSource;
  relevantSources: ChatSource[];
  mentionedPath?: string;
} {
  // 1. Check for explicit endpoint path mentions (owner/slug)
  const mentionedPaths = parseEndpointMentions(query);
  for (const path of mentionedPaths) {
    const matched = findEndpointByPath(availableSources, path);
    if (matched) {
      return {
        action: 'auto-select',
        matchedEndpoint: matched,
        relevantSources: [matched],
        mentionedPath: path
      };
    }
  }

  // 2. Check for exact endpoint name matches
  const nameMatch = findEndpointByQueryWords(query, availableSources);
  if (nameMatch) {
    return {
      action: 'auto-select',
      matchedEndpoint: nameMatch,
      relevantSources: [nameMatch]
    };
  }

  // 3. Filter by relevance
  const relevantSources = filterRelevantSources(availableSources, query);

  if (relevantSources.length > 0 && relevantSources.length < availableSources.length) {
    return {
      action: 'show-relevant',
      relevantSources
    };
  }

  // 4. No specific matches, show all
  return {
    action: 'show-all',
    relevantSources: availableSources
  };
}
