/**
 * Datasite API Client - Connects to SyftHub backend datasite endpoints
 */

import type {
  ChatSource,
  DatasiteCreate,
  DatasiteFilters,
  DatasitePublicResponse,
  DatasiteResponse,
  DatasiteUpdate,
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

// Utility function to convert backend DatasitePublicResponse to frontend ChatSource
export function mapDatasiteToSource(datasite: DatasitePublicResponse): ChatSource {
  // Determine tag from policies (first policy type or fallback to "General")
  const policies = datasite.policies ?? [];
  const firstPolicy = policies[0];
  const tag = firstPolicy
    ? firstPolicy.type.charAt(0).toUpperCase() + firstPolicy.type.slice(1)
    : 'General';

  // Determine status based on updated time and policies
  const updatedDate = new Date(datasite.updated_at);
  const daysSinceUpdate = Math.floor((Date.now() - updatedDate.getTime()) / (1000 * 60 * 60 * 24));

  let status: 'active' | 'warning' | 'inactive' = 'active';
  if (daysSinceUpdate > 7) status = 'warning';
  if (daysSinceUpdate > 30) status = 'inactive';

  // Use provided owner_username or default
  const ownerUsername = datasite.owner_username ?? 'anonymous';
  const fullPath = `${ownerUsername}/${datasite.slug}`;

  return {
    id: datasite.slug, // Use slug as unique identifier
    name: datasite.name,
    tag: tag,
    description: datasite.description,
    updated: formatRelativeTime(updatedDate),
    status: status,
    slug: datasite.slug,
    stars_count: datasite.stars_count,
    version: datasite.version,
    contributors: [], // Contributors not exposed in public response for privacy
    owner_username: ownerUsername,
    full_path: fullPath
  };
}

// Get public datasites (no authentication required)
export async function getPublicDatasites(params: PaginationParams = {}): Promise<ChatSource[]> {
  const { skip = 0, limit = 10 } = params;

  const queryParams = new URLSearchParams();
  if (skip > 0) queryParams.set('skip', String(skip));
  if (limit !== 10) queryParams.set('limit', String(limit));

  const queryString = queryParams.toString();
  const baseUrl = API_CONFIG.ENDPOINTS.DATASITES.PUBLIC;
  const url = queryString ? `${baseUrl}?${queryString}` : baseUrl;

  const datasites = await apiClient.get<DatasitePublicResponse[]>(url, false); // No auth required
  return datasites.map((ds) => mapDatasiteToSource(ds));
}

// Get trending datasites (no authentication required)
export async function getTrendingDatasites(
  params: PaginationParams & { min_stars?: number } = {}
): Promise<ChatSource[]> {
  const { skip = 0, limit = 10, min_stars } = params;

  const queryParams = new URLSearchParams();
  if (skip > 0) queryParams.set('skip', String(skip));
  if (limit !== 10) queryParams.set('limit', String(limit));
  if (min_stars !== undefined) queryParams.set('min_stars', String(min_stars));

  const queryString = queryParams.toString();
  const baseUrl = API_CONFIG.ENDPOINTS.DATASITES.TRENDING;
  const url = queryString ? `${baseUrl}?${queryString}` : baseUrl;

  const datasites = await apiClient.get<DatasitePublicResponse[]>(url, false); // No auth required
  return datasites.map((ds) => mapDatasiteToSource(ds));
}

// Get user's datasites (authentication required)
export async function getUserDatasites(filters: DatasiteFilters = {}): Promise<DatasiteResponse[]> {
  const { skip = 0, limit = 10, search, visibility } = filters;

  const queryParams = new URLSearchParams();
  if (skip > 0) queryParams.set('skip', String(skip));
  if (limit !== 10) queryParams.set('limit', String(limit));
  if (search) queryParams.set('search', search);
  if (visibility) queryParams.set('visibility', visibility);

  const queryString = queryParams.toString();
  const baseUrl = API_CONFIG.ENDPOINTS.DATASITES.LIST;
  const url = queryString ? `${baseUrl}?${queryString}` : baseUrl;

  return await apiClient.get<DatasiteResponse[]>(url);
}

// Get specific datasite by ID (authentication required)
export async function getDatasite(id: number): Promise<DatasiteResponse> {
  return await apiClient.get<DatasiteResponse>(API_CONFIG.ENDPOINTS.DATASITES.BY_ID(id));
}

// Create new datasite (authentication required)
export async function createDatasite(
  datasiteData: DatasiteCreate,
  organizationId?: number
): Promise<DatasiteResponse> {
  const url = organizationId
    ? `${API_CONFIG.ENDPOINTS.DATASITES.CREATE}?organization_id=${String(organizationId)}`
    : API_CONFIG.ENDPOINTS.DATASITES.CREATE;

  return await apiClient.post<DatasiteResponse>(url, datasiteData);
}

// Update datasite (authentication required)
export async function updateDatasite(
  id: number,
  updateData: DatasiteUpdate
): Promise<DatasiteResponse> {
  return await apiClient.patch<DatasiteResponse>(
    API_CONFIG.ENDPOINTS.DATASITES.BY_ID(id),
    updateData
  );
}

// Delete datasite (authentication required)
export async function deleteDatasite(id: number): Promise<void> {
  await apiClient.delete<null>(API_CONFIG.ENDPOINTS.DATASITES.BY_ID(id));
}

// Utility function to get mixed data sources for chat (combines public and trending)
export async function getChatDataSources(limit = 20): Promise<ChatSource[]> {
  try {
    // Get half trending and half public datasites
    const trendingLimit = Math.floor(limit / 2);
    const publicLimit = limit - trendingLimit;

    const [trending, publicDatasites] = await Promise.all([
      getTrendingDatasites({ limit: trendingLimit }),
      getPublicDatasites({ limit: publicLimit })
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

    // Add public datasites that aren't already included
    for (const source of publicDatasites) {
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
