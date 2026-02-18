/**
 * Type definitions matching the SyftHub backend API schemas
 */

// User Role enum
export type UserRole = 'admin' | 'user' | 'guest';

// User interfaces matching backend User schema
export interface BackendUser {
  id: number; // Backend uses int, not string
  username: string;
  email: string;
  full_name: string; // Backend uses full_name, not name
  avatar_url?: string; // URL to user's avatar image
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
  avatar_url?: string;
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
  avatar_url?: string; // URL to user's avatar image
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  /** Domain for endpoint URL construction (e.g., "api.example.com:8080") */
  domain?: string;
  /** Custom aggregator URL for RAG/chat workflows */
  aggregator_url?: string;
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

// User profile update
export interface UserUpdate {
  username?: string;
  email?: string;
  full_name?: string;
  avatar_url?: string;
  /** Domain for endpoint URL construction (no protocol) */
  domain?: string;
  /** Custom aggregator URL for RAG/chat workflows */
  aggregator_url?: string;
}

// =============================================================================
// User Aggregator Types
// =============================================================================

/** User aggregator configuration */
export interface UserAggregator {
  id: number;
  user_id: number;
  name: string;
  url: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

/** Request to create a new user aggregator */
export interface UserAggregatorCreate {
  name: string;
  url: string;
  is_default?: boolean;
}

/** Request to update an existing user aggregator */
export interface UserAggregatorUpdate {
  name?: string;
  url?: string;
  is_default?: boolean;
}

/** Response containing list of user aggregators */
export interface UserAggregatorListResponse {
  aggregators: UserAggregator[];
  default_aggregator_id: number | null;
}

// Availability check responses
export interface AvailabilityResponse {
  available: boolean;
  username?: string;
  email?: string;
}

// Endpoint visibility levels
export type EndpointVisibility = 'public' | 'private' | 'internal';

// Endpoint type classification
export type EndpointType = 'model' | 'data_source' | 'model_data_source';

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
  type: EndpointType;
  visibility: EndpointVisibility;
  version: string;
  readme: string;
  tags: string[];
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
  tags?: string[];
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
  type: EndpointType;
  /** Number of contributors (user IDs not exposed for privacy) */
  contributors_count: number;
  version: string;
  readme: string;
  tags: string[];
  stars_count: number;
  policies: Policy[];
  connect: Connection[];
  created_at: string;
  updated_at: string;
  owner_username?: string; // Username of the endpoint owner (if exposed by backend)
}

// =============================================================================
// Grouped Endpoints Types (for Global Directory)
// =============================================================================

/**
 * A group of endpoints belonging to a single owner.
 * Used in the grouped public endpoints response for the Global Directory.
 */
export interface EndpointGroup {
  /** Username of the endpoint owner */
  owner_username: string;
  /** Endpoints belonging to this owner (limited to max_per_owner) */
  endpoints: ChatSource[];
  /** Total number of endpoints this owner has (may be more than shown) */
  total_count: number;
  /** True if owner has more endpoints than shown */
  has_more: boolean;
}

/**
 * Response containing endpoints grouped by owner.
 * Used for the Global Directory to display a balanced view across multiple owners.
 */
export interface GroupedEndpointsResponse {
  /** Endpoint groups ordered by total endpoint count (descending) */
  groups: EndpointGroup[];
}

// Frontend ChatSource interface (mapped from EndpointPublicResponse)
export interface ChatSource {
  id: string; // Use slug as ID for frontend
  name: string;
  tags: string[]; // Tags for categorization
  description: string;
  type: EndpointType; // Endpoint type (model or data_source)
  updated: string; // Mapped from updated_at
  status: 'active' | 'warning' | 'inactive'; // Derived from backend data
  slug: string; // Backend URL identifier
  stars_count: number;
  version: string;
  readme: string; // Markdown content for documentation
  /** Number of contributors (user IDs not exposed for privacy) */
  contributors_count: number;
  owner_username?: string; // Username of the endpoint owner
  full_path?: string; // Full path: username/endpoint-name
  url?: string; // Connection URL from connect[0].config.url (if available)
  tenant_name?: string; // Tenant name from connect[0].config.tenant_name (for SyftAI-Space multi-tenancy)
  connections?: Connection[]; // Full connection configurations (for detailed view)
  policies?: Policy[]; // Access policies for the endpoint
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

// =============================================================================
// Accounting / Payment Types
// =============================================================================

/**
 * Credentials for connecting to an external accounting service.
 * These are stored in the SyftHub backend and fetched via API.
 * The email is the same as the user's SyftHub email.
 */
export interface AccountingCredentials {
  /** URL of the accounting service API (null if not configured) */
  url: string | null;
  /** Email for authenticating with the accounting service (same as SyftHub email) */
  email: string;
  /** Password for authenticating with the accounting service (null if not configured) */
  password: string | null;
}

// =============================================================================
// Accounting API Types (for interacting with external accounting service)
// =============================================================================

/**
 * Transaction status in the accounting service.
 */
export type TransactionStatus = 'pending' | 'completed' | 'cancelled';

/**
 * Who created or resolved a transaction.
 */
export type CreatorType = 'system' | 'sender' | 'recipient';

/**
 * User from accounting service with balance.
 * This is separate from the SyftHub User type.
 */
export interface AccountingUser {
  id: string;
  email: string;
  balance: number;
  organization: string | null;
}

/**
 * Transaction record from accounting service.
 */
export interface AccountingTransaction {
  id: string;
  senderEmail: string;
  recipientEmail: string;
  amount: number;
  status: TransactionStatus;
  createdBy: CreatorType;
  resolvedBy: CreatorType | null;
  createdAt: Date;
  resolvedAt: Date | null;
  appName: string | null;
  appEpPath: string | null;
}

/**
 * Input for creating a direct transaction.
 */
export interface CreateTransactionInput {
  recipientEmail: string;
  amount: number;
  appName?: string;
  appEpPath?: string;
}

/**
 * Input for creating a delegated transaction.
 */
export interface CreateDelegatedTransactionInput {
  senderEmail: string;
  amount: number;
  token: string;
}

/**
 * State for accounting API operations
 */
export interface AccountingAPIState {
  /** Current user from accounting service */
  user: AccountingUser | null;
  /** Recent transactions */
  transactions: AccountingTransaction[];
  /** Currently active (pending) transaction */
  pendingTransaction: AccountingTransaction | null;
  /** Whether API operations are in progress */
  isLoading: boolean;
  /** API error (separate from vault errors) */
  apiError: string | null;
}
