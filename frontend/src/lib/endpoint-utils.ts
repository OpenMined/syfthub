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
 * - Tag extraction from policies
 * - URL extraction from connect config
 */
export function mapEndpointPublicToSource(endpoint: SdkEndpointPublic): ChatSource {
  // Determine tag from policies (first policy type or fallback to "General")
  const policies = endpoint.policies;
  const firstPolicy = policies[0];
  const tag = firstPolicy
    ? firstPolicy.type.charAt(0).toUpperCase() + firstPolicy.type.slice(1)
    : 'General';

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

  return {
    id: endpoint.slug,
    name: endpoint.name,
    tag: tag,
    description: endpoint.description,
    type: endpoint.type,
    updated: formatRelativeTime(updatedDate),
    status: status,
    slug: endpoint.slug,
    stars_count: endpoint.starsCount,
    version: endpoint.version,
    contributors: [],
    owner_username: ownerUsername,
    full_path: fullPath,
    url: url,
    tenant_name: tenantName,
    connections: mappedConnections
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
 * Get public endpoints from the hub.
 *
 * @param params - Pagination and filter parameters
 * @returns Array of ChatSource objects
 */
export async function getPublicEndpoints(
  params: PaginationParams & { endpoint_type?: EndpointType } = {}
): Promise<ChatSource[]> {
  const { limit = 10 } = params;

  try {
    // Note: SDK doesn't support endpoint_type filter yet, we filter client-side
    const endpoints = await syftClient.hub.browse({ pageSize: limit }).firstPage();

    let results = endpoints.map((ep) => mapEndpointPublicToSource(ep));

    // Client-side type filtering if specified
    if (params.endpoint_type) {
      results = results.filter((ep) => ep.type === params.endpoint_type);
    }

    return results;
  } catch (error) {
    console.error('Failed to fetch public endpoints:', error);
    return [];
  }
}

/**
 * Get trending endpoints sorted by stars.
 *
 * @param params - Pagination and filter parameters
 * @returns Array of ChatSource objects
 */
export async function getTrendingEndpoints(
  params: PaginationParams & { min_stars?: number; endpoint_type?: EndpointType } = {}
): Promise<ChatSource[]> {
  const { limit = 10, min_stars } = params;

  try {
    const endpoints = await syftClient.hub
      .trending({ minStars: min_stars, pageSize: limit })
      .firstPage();

    let results = endpoints.map((ep) => mapEndpointPublicToSource(ep));

    // Client-side type filtering if specified
    if (params.endpoint_type) {
      results = results.filter((ep) => ep.type === params.endpoint_type);
    }

    return results;
  } catch (error) {
    console.error('Failed to fetch trending endpoints:', error);
    return [];
  }
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
// Legacy ID-based Functions (For backward compatibility)
// ============================================================================

/**
 * Update an endpoint by ID.
 *
 * @deprecated Use updateEndpointByPath instead for better performance.
 * @param id - Endpoint ID (requires additional API call to resolve path)
 * @param updateData - Fields to update
 * @param ownerUsername - Username of the endpoint owner
 * @param slug - Slug of the endpoint
 * @returns Updated EndpointResponse
 */
export async function updateEndpoint(
  _id: number,
  updateData: EndpointUpdate,
  ownerUsername: string,
  slug: string
): Promise<EndpointResponse> {
  const path = `${ownerUsername}/${slug}`;
  return updateEndpointByPath(path, updateData);
}

/**
 * Delete an endpoint by ID.
 *
 * @deprecated Use deleteEndpointByPath instead for better performance.
 * @param id - Endpoint ID (not actually used, kept for signature compatibility)
 * @param ownerUsername - Username of the endpoint owner
 * @param slug - Slug of the endpoint
 */
export async function deleteEndpoint(
  _id: number,
  ownerUsername: string,
  slug: string
): Promise<void> {
  const path = `${ownerUsername}/${slug}`;
  await deleteEndpointByPath(path);
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

    // Combine and deduplicate by slug
    const combinedSources: ChatSource[] = [];
    const seenSlugs = new Set<string>();

    // Add trending first (higher priority)
    for (const source of trending) {
      if (!seenSlugs.has(source.slug)) {
        seenSlugs.add(source.slug);
        combinedSources.push(source);
      }
    }

    // Add public endpoints that aren't already included
    for (const source of publicEndpoints) {
      if (!seenSlugs.has(source.slug)) {
        seenSlugs.add(source.slug);
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

    // Combine and deduplicate by slug
    const combinedModels: ChatSource[] = [];
    const seenSlugs = new Set<string>();

    // Add trending first (higher priority)
    for (const model of trending) {
      if (!seenSlugs.has(model.slug)) {
        seenSlugs.add(model.slug);
        combinedModels.push(model);
      }
    }

    // Add public endpoints that aren't already included
    for (const model of publicEndpoints) {
      if (!seenSlugs.has(model.slug)) {
        seenSlugs.add(model.slug);
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
// Re-export for backward compatibility
// ============================================================================

// Keep the old function name as alias
export { mapEndpointPublicToSource as mapEndpointToSource };
