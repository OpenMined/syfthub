import type { UserRole } from './common.js';

/**
 * User account information.
 */
export interface User {
  readonly id: number;
  readonly username: string;
  readonly email: string;
  readonly fullName: string;
  readonly avatarUrl: string | null;
  readonly role: UserRole;
  readonly isActive: boolean;
  readonly createdAt: Date;
  readonly updatedAt: Date | null;
}

/**
 * Authentication tokens returned from login/register.
 */
export interface AuthTokens {
  readonly accessToken: string;
  readonly refreshToken: string;
  readonly tokenType: string;
}

/**
 * Input for user registration.
 */
export interface UserRegisterInput {
  username: string;
  email: string;
  password: string;
  fullName: string;
}

/**
 * Input for updating user profile.
 */
export interface UserUpdateInput {
  username?: string;
  email?: string;
  fullName?: string;
  avatarUrl?: string;
}

/**
 * Input for changing password.
 */
export interface PasswordChangeInput {
  currentPassword: string;
  newPassword: string;
}
