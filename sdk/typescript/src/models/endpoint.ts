import type { EndpointType, Visibility } from './common.js';

/**
 * Policy configuration for an endpoint.
 */
export interface Policy {
  readonly type: string;
  readonly version: string;
  readonly enabled: boolean;
  readonly description: string;
  readonly config: Record<string, unknown>;
}

/**
 * Connection configuration for an endpoint.
 */
export interface Connection {
  readonly type: string;
  readonly enabled: boolean;
  readonly description: string;
  readonly config: Record<string, unknown>;
}

/**
 * Full endpoint model (for authenticated users viewing their own endpoints).
 */
export interface Endpoint {
  readonly id: number;
  readonly userId: number | null;
  readonly organizationId: number | null;
  readonly name: string;
  readonly slug: string;
  readonly description: string;
  readonly type: EndpointType;
  readonly visibility: Visibility;
  readonly isActive: boolean;
  readonly contributors: readonly number[];
  readonly version: string;
  readonly readme: string;
  readonly tags: readonly string[];
  readonly starsCount: number;
  readonly policies: readonly Policy[];
  readonly connect: readonly Connection[];
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

/**
 * Public endpoint model (for browsing the hub).
 */
export interface EndpointPublic {
  readonly name: string;
  readonly slug: string;
  readonly description: string;
  readonly type: EndpointType;
  readonly ownerUsername: string;
  /** Number of contributors (user IDs not exposed for privacy) */
  readonly contributorsCount: number;
  readonly version: string;
  readonly readme: string;
  readonly tags: readonly string[];
  readonly starsCount: number;
  readonly policies: readonly Policy[];
  readonly connect: readonly Connection[];
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

/**
 * Input for creating a new endpoint.
 */
export interface EndpointCreateInput {
  name: string;
  type: EndpointType;
  visibility?: Visibility;
  description?: string;
  slug?: string;
  version?: string;
  readme?: string;
  tags?: string[];
  policies?: Policy[];
  connect?: Connection[];
  contributors?: number[];
}

/**
 * Input for updating an existing endpoint.
 */
export interface EndpointUpdateInput {
  name?: string;
  description?: string;
  visibility?: Visibility;
  version?: string;
  readme?: string;
  tags?: string[];
  policies?: Policy[];
  connect?: Connection[];
  contributors?: number[];
}

/**
 * Get the owner type for an endpoint.
 *
 * @param endpoint - The endpoint to check
 * @returns 'user' if user-owned, 'organization' if org-owned
 */
export function getEndpointOwnerType(endpoint: Endpoint): 'user' | 'organization' {
  return endpoint.organizationId !== null ? 'organization' : 'user';
}

/**
 * Get the full path for a public endpoint (owner/slug format).
 *
 * @param endpoint - The public endpoint
 * @returns The path in "owner/slug" format
 */
export function getEndpointPublicPath(endpoint: EndpointPublic): string {
  return `${endpoint.ownerUsername}/${endpoint.slug}`;
}
