/**
 * Visibility levels for endpoints.
 */
export const Visibility = {
  /** Visible to everyone, no authentication required */
  PUBLIC: 'public',
  /** Only visible to the owner and collaborators */
  PRIVATE: 'private',
  /** Visible to authenticated users within the organization */
  INTERNAL: 'internal',
} as const;

export type Visibility = (typeof Visibility)[keyof typeof Visibility];

/**
 * Types of endpoints.
 */
export const EndpointType = {
  /** Machine learning model endpoint */
  MODEL: 'model',
  /** Data source endpoint */
  DATA_SOURCE: 'data_source',
  /** Both model and data source endpoint */
  MODEL_DATA_SOURCE: 'model_data_source',
} as const;

export type EndpointType = (typeof EndpointType)[keyof typeof EndpointType];

/**
 * User roles in the system.
 */
export const UserRole = {
  /** Administrator with full access */
  ADMIN: 'admin',
  /** Regular user */
  USER: 'user',
  /** Guest user with limited access */
  GUEST: 'guest',
} as const;

export type UserRole = (typeof UserRole)[keyof typeof UserRole];

/**
 * Organization member roles.
 */
export const OrganizationRole = {
  /** Organization owner with full control */
  OWNER: 'owner',
  /** Administrator with management privileges */
  ADMIN: 'admin',
  /** Regular member */
  MEMBER: 'member',
} as const;

export type OrganizationRole = (typeof OrganizationRole)[keyof typeof OrganizationRole];
