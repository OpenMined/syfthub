/**
 * Type definitions matching the SyftHub backend API schemas
 */

// User Role enum
export type UserRole = 'admin' | 'user' | 'guest';

// User interfaces matching backend User schema
export interface BackendUser {
  id: number; // Backend uses int, not string
  username: string; // New field required by backend
  email: string;
  full_name: string; // Backend uses full_name, not name
  age?: number; // New optional field
  role: UserRole;
  is_active: boolean;
  created_at: string; // ISO datetime string
  updated_at: string; // ISO datetime string
}

// User response schema from backend
export interface UserResponse {
  id: number;
  username: string;
  email: string;
  full_name: string;
  age?: number;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// Frontend User interface (mapped from backend)
export interface User {
  id: string; // Convert from number for frontend compatibility
  username: string;
  email: string;
  name: string; // Mapped from full_name
  full_name: string; // Keep original for API calls
  age?: number;
  role: UserRole;
  avatar?: string; // Generated or provided
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// Authentication request schemas
export interface LoginRequest {
  username: string; // Backend expects username (not email) for OAuth2
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  full_name: string;
  password: string;
  age?: number;
}

// Authentication response schemas
export interface AuthResponse {
  user: BackendUser;
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export type RegistrationResponse = AuthResponse;

// Token management
export interface TokenData {
  username?: string;
  user_id?: number;
  role?: UserRole;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

// Password change
export interface PasswordChange {
  current_password: string;
  new_password: string;
}

// Endpoint visibility levels
export type EndpointVisibility = 'public' | 'private' | 'internal';

// Policy and Connection types for endpoints
export interface Policy {
  type: string;
  version: string;
  enabled: boolean;
  description: string;
  config: Record<string, unknown>;
}

export interface Connection {
  type: string;
  enabled: boolean;
  description: string;
  config: Record<string, unknown>;
}

// Endpoint schemas
export interface EndpointBase {
  name: string;
  description: string;
  visibility: EndpointVisibility;
  version: string;
  readme: string;
  policies: Policy[];
  connect: Connection[];
}

export interface EndpointCreate extends EndpointBase {
  slug?: string; // Optional, auto-generated if not provided
  contributors: number[]; // User IDs
}

export interface EndpointUpdate {
  name?: string;
  description?: string;
  visibility?: EndpointVisibility;
  contributors?: number[];
  version?: string;
  readme?: string;
  policies?: Policy[];
  connect?: Connection[];
}

export interface Endpoint extends EndpointBase {
  id: number;
  user_id?: number;
  organization_id?: number;
  slug: string;
  is_active: boolean;
  contributors: number[];
  stars_count: number;
  created_at: string;
  updated_at: string;
}

export type EndpointResponse = Endpoint;

export interface EndpointPublicResponse {
  name: string;
  slug: string;
  description: string;
  contributors: number[];
  version: string;
  readme: string;
  stars_count: number;
  policies: Policy[];
  connect: Connection[];
  created_at: string;
  updated_at: string;
  owner_username?: string; // Username of the endpoint owner (if exposed by backend)
}

// Frontend ChatSource interface (mapped from EndpointPublicResponse)
export interface ChatSource {
  id: string; // Use slug as ID for frontend
  name: string;
  tag: string; // Derived from policies/categories
  description: string;
  updated: string; // Mapped from updated_at
  status: 'active' | 'warning' | 'inactive'; // Derived from backend data
  slug: string; // Backend URL identifier
  stars_count: number;
  version: string;
  contributors: number[];
  owner_username?: string; // Username of the endpoint owner
  full_path?: string; // Full path: username/endpoint-name
}

// Organization types
export type OrganizationRole = 'owner' | 'admin' | 'member';

export interface Organization {
  id: number;
  name: string;
  slug: string;
  description: string;
  avatar_url?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OrganizationCreate {
  name: string;
  description: string;
  avatar_url?: string;
}

export interface OrganizationUpdate {
  name?: string;
  description?: string;
  avatar_url?: string;
  is_active?: boolean;
}

export interface OrganizationMember {
  id: number;
  organization_id: number;
  user_id: number;
  role: OrganizationRole;
  joined_at: string;
  user?: UserResponse; // Populated in responses
}

export interface OrganizationMemberCreate {
  user_id: number;
  role: OrganizationRole;
}

export interface OrganizationMemberUpdate {
  role?: OrganizationRole;
}

// API Error interface
export interface APIErrorResponse {
  detail: string;
  type?: string;
  field?: string;
}

// Utility type for API responses
export type APIResponse<T> = T;

// Pagination params
export interface PaginationParams {
  skip?: number;
  limit?: number;
}

// Search params
export interface SearchParams extends PaginationParams {
  search?: string;
}

// Endpoint filters
export interface EndpointFilters extends SearchParams {
  visibility?: EndpointVisibility;
  min_stars?: number;
}

// Organization filters
export interface OrganizationFilters extends SearchParams {
  role?: OrganizationRole;
}
