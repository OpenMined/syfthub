/**
 * Endpoint API Client - Connects to SyftHub backend endpoint endpoints
 */

import type {
  ChatSource,
  EndpointCreate,
  EndpointFilters,
  EndpointPublicResponse,
  EndpointResponse,
  EndpointType,
  EndpointUpdate,
  PaginationParams
} from './types';

import { API_CONFIG, apiClient } from './api-client';

// Helper to format relative time
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

// Utility function to convert backend EndpointPublicResponse to frontend ChatSource
export function mapEndpointToSource(endpoint: EndpointPublicResponse): ChatSource {
  // Determine tag from policies (first policy type or fallback to "General")
  const policies = endpoint.policies ?? [];
  const firstPolicy = policies[0];
  const tag = firstPolicy
    ? firstPolicy.type.charAt(0).toUpperCase() + firstPolicy.type.slice(1)
    : 'General';

  // Determine status based on updated time and policies
  const updatedDate = new Date(endpoint.updated_at);
  const daysSinceUpdate = Math.floor((Date.now() - updatedDate.getTime()) / (1000 * 60 * 60 * 24));

  let status: 'active' | 'warning' | 'inactive' = 'active';
  if (daysSinceUpdate > 7) status = 'warning';
  if (daysSinceUpdate > 30) status = 'inactive';

  // Use provided owner_username or default
  const ownerUsername = endpoint.owner_username ?? 'anonymous';
  const fullPath = `${ownerUsername}/${endpoint.slug}`;

  return {
    id: endpoint.slug, // Use slug as unique identifier
    name: endpoint.name,
    tag: tag,
    description: endpoint.description,
    type: endpoint.type,
    updated: formatRelativeTime(updatedDate),
    status: status,
    slug: endpoint.slug,
    stars_count: endpoint.stars_count,
    version: endpoint.version,
    contributors: [], // Contributors not exposed in public response for privacy
    owner_username: ownerUsername,
    full_path: fullPath
  };
}

// Get public endpoints (no authentication required)
export async function getPublicEndpoints(
  params: PaginationParams & { endpoint_type?: EndpointType } = {}
): Promise<ChatSource[]> {
  const { skip = 0, limit = 10, endpoint_type } = params;

  const queryParams = new URLSearchParams();
  if (skip > 0) queryParams.set('skip', String(skip));
  if (limit !== 10) queryParams.set('limit', String(limit));
  if (endpoint_type) queryParams.set('endpoint_type', endpoint_type);

  const queryString = queryParams.toString();
  const baseUrl = API_CONFIG.ENDPOINTS.ENDPOINTS.PUBLIC;
  const url = queryString ? `${baseUrl}?${queryString}` : baseUrl;

  const endpoints = await apiClient.get<EndpointPublicResponse[]>(url, false); // No auth required
  return endpoints.map((ds) => mapEndpointToSource(ds));
}

// Get trending endpoints (no authentication required)
export async function getTrendingEndpoints(
  params: PaginationParams & { min_stars?: number; endpoint_type?: EndpointType } = {}
): Promise<ChatSource[]> {
  const { skip = 0, limit = 10, min_stars, endpoint_type } = params;

  const queryParams = new URLSearchParams();
  if (skip > 0) queryParams.set('skip', String(skip));
  if (limit !== 10) queryParams.set('limit', String(limit));
  if (min_stars !== undefined) queryParams.set('min_stars', String(min_stars));
  if (endpoint_type) queryParams.set('endpoint_type', endpoint_type);

  const queryString = queryParams.toString();
  const baseUrl = API_CONFIG.ENDPOINTS.ENDPOINTS.TRENDING;
  const url = queryString ? `${baseUrl}?${queryString}` : baseUrl;

  const endpoints = await apiClient.get<EndpointPublicResponse[]>(url, false); // No auth required
  return endpoints.map((ds) => mapEndpointToSource(ds));
}

// Get user's endpoints (authentication required)
export async function getUserEndpoints(filters: EndpointFilters = {}): Promise<EndpointResponse[]> {
  const { skip = 0, limit = 10, search, visibility } = filters;

  const queryParams = new URLSearchParams();
  if (skip > 0) queryParams.set('skip', String(skip));
  if (limit !== 10) queryParams.set('limit', String(limit));
  if (search) queryParams.set('search', search);
  if (visibility) queryParams.set('visibility', visibility);

  const queryString = queryParams.toString();
  const baseUrl = API_CONFIG.ENDPOINTS.ENDPOINTS.LIST;
  const url = queryString ? `${baseUrl}?${queryString}` : baseUrl;

  return await apiClient.get<EndpointResponse[]>(url);
}

// Get specific endpoint by ID (authentication required)
export async function getEndpoint(id: number): Promise<EndpointResponse> {
  return await apiClient.get<EndpointResponse>(API_CONFIG.ENDPOINTS.ENDPOINTS.BY_ID(id));
}

// Create new endpoint (authentication required)
export async function createEndpoint(
  endpointData: EndpointCreate,
  organizationId?: number
): Promise<EndpointResponse> {
  const url = organizationId
    ? `${API_CONFIG.ENDPOINTS.ENDPOINTS.CREATE}?organization_id=${String(organizationId)}`
    : API_CONFIG.ENDPOINTS.ENDPOINTS.CREATE;

  return await apiClient.post<EndpointResponse>(url, endpointData);
}

// Update endpoint (authentication required)
export async function updateEndpoint(
  id: number,
  updateData: EndpointUpdate
): Promise<EndpointResponse> {
  return await apiClient.patch<EndpointResponse>(
    API_CONFIG.ENDPOINTS.ENDPOINTS.BY_ID(id),
    updateData
  );
}

// Delete endpoint (authentication required)
export async function deleteEndpoint(id: number): Promise<void> {
  await apiClient.delete<null>(API_CONFIG.ENDPOINTS.ENDPOINTS.BY_ID(id));
}

// Utility function to get data sources for chat (combines public and trending data_source endpoints)
export async function getChatDataSources(limit = 20): Promise<ChatSource[]> {
  try {
    // Get half trending and half public endpoints, filtered to data_source type only
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
    // Return empty array on error - UI can handle gracefully
    return [];
  }
}

// Utility function to get model endpoints for chat (combines public and trending model endpoints)
export async function getChatModels(limit = 20): Promise<ChatSource[]> {
  try {
    // Get half trending and half public endpoints, filtered to model type only
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
    // Return empty array on error - UI can handle gracefully
    return [];
  }
}
