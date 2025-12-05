import type { AccountingCredentials, AccountingError, AccountingVaultStatus } from './types';

import {
  CryptoNotSupportedError,
  decrypt,
  encrypt,
  InvalidPinError,
  isCryptoSupported,
  parseVault,
  serializeVault,
  VaultCorruptedError
} from './crypto-vault';

/**
 * Accounting Storage Module
 *
 * High-level API for managing encrypted accounting credentials.
 * Uses crypto-vault.ts for encryption and browser storage for persistence.
 *
 * Storage Strategy:
 * - localStorage: Encrypted vault (persists across browser sessions)
 * - sessionStorage: Decrypted credentials (tab-scoped, cleared on tab close)
 *
 * Security Features:
 * - Credentials encrypted at rest with AES-256-GCM
 * - Plaintext only available in current tab's sessionStorage
 * - Rate limiting on unlock attempts (exponential backoff)
 * - Auto-lock after configurable inactivity period
 */

// =============================================================================
// Storage Keys
// =============================================================================

const STORAGE_KEYS = {
  /** Encrypted vault in localStorage */
  VAULT: 'syft_accounting_vault',
  /** Decrypted credentials in sessionStorage */
  SESSION: 'syft_accounting_session',
  /** Number of unlock attempts in sessionStorage */
  ATTEMPTS: 'syft_vault_attempts',
  /** Timestamp of last unlock attempt in sessionStorage */
  LAST_ATTEMPT: 'syft_vault_last_attempt',
  /** Timestamp of last user activity in sessionStorage */
  ACTIVITY: 'syft_vault_activity'
} as const;

// =============================================================================
// Rate Limiting Configuration
// =============================================================================

/**
 * Delay in seconds after N failed attempts
 * Index 0-2: No delay (first 3 attempts)
 * Index 3: 5 seconds
 * Index 4: 10 seconds
 * Index 5: 30 seconds
 * Index 6+: 60 seconds
 */
const RATE_LIMIT_DELAYS = [0, 0, 0, 5, 10, 30, 60] as const;

/** Default auto-lock timeout in minutes */
const DEFAULT_AUTO_LOCK_TIMEOUT = 15;

// =============================================================================
// Storage Helpers
// =============================================================================

/**
 * Safely get item from localStorage
 */
function getLocalStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/**
 * Safely set item in localStorage
 */
function setLocalStorage(key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

/**
 * Safely remove item from localStorage
 */
function removeLocalStorage(key: string): boolean {
  try {
    localStorage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

/**
 * Safely get item from sessionStorage
 */
function getSessionStorage(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

/**
 * Safely set item in sessionStorage
 */
function setSessionStorage(key: string, value: string): boolean {
  try {
    sessionStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

/**
 * Safely remove item from sessionStorage
 */
function removeSessionStorage(key: string): boolean {
  try {
    sessionStorage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

// =============================================================================
// Custom Error Class
// =============================================================================

/**
 * Custom error class for accounting storage operations
 */
export class AccountingStorageError extends Error implements AccountingError {
  type: AccountingError['type'];
  field?: string;
  waitTime?: number;

  constructor(accountingError: AccountingError) {
    super(accountingError.message);
    this.name = 'AccountingStorageError';
    this.type = accountingError.type;
    this.field = accountingError.field;
    this.waitTime = accountingError.waitTime;
    Object.setPrototypeOf(this, AccountingStorageError.prototype);
  }
}

// =============================================================================
// Error Conversion
// =============================================================================

/**
 * Convert crypto errors to AccountingStorageError
 */
function toAccountingError(error: unknown): AccountingStorageError {
  if (error instanceof InvalidPinError) {
    return new AccountingStorageError({
      type: 'INVALID_PIN',
      message: 'Incorrect PIN. Please try again.'
    });
  }

  if (error instanceof CryptoNotSupportedError) {
    return new AccountingStorageError({
      type: 'CRYPTO_NOT_SUPPORTED',
      message: 'Your browser does not support secure encryption. Please use a modern browser.'
    });
  }

  if (error instanceof VaultCorruptedError) {
    return new AccountingStorageError({
      type: 'VAULT_CORRUPTED',
      message: 'Vault data appears corrupted. You may need to delete and recreate it.'
    });
  }

  return new AccountingStorageError({
    type: 'STORAGE_UNAVAILABLE',
    message: error instanceof Error ? error.message : 'An unknown error occurred.'
  });
}

// =============================================================================
// AccountingStorage Class
// =============================================================================

/**
 * Static class for managing accounting credentials with encrypted storage.
 * Uses static methods only as this is a utility class with no instance state.
 */
// eslint-disable-next-line @typescript-eslint/no-extraneous-class
export class AccountingStorage {
  // ===========================================================================
  // Status Methods
  // ===========================================================================

  /**
   * Get current vault status
   */
  static getStatus(): AccountingVaultStatus {
    const hasVault = this.hasVault();
    const isUnlocked = this.isUnlocked();

    return {
      isConfigured: hasVault,
      isUnlocked: isUnlocked,
      isLocked: hasVault && !isUnlocked,
      isEmpty: !hasVault
    };
  }

  /**
   * Check if a vault exists in localStorage
   */
  static hasVault(): boolean {
    const vault = getLocalStorage(STORAGE_KEYS.VAULT);
    return vault !== null && vault.length > 0;
  }

  /**
   * Check if vault is unlocked (credentials in sessionStorage)
   */
  static isUnlocked(): boolean {
    const session = getSessionStorage(STORAGE_KEYS.SESSION);
    return session !== null && session.length > 0;
  }

  /**
   * Check if Web Crypto API is available
   */
  static isCryptoSupported(): boolean {
    return isCryptoSupported();
  }

  // ===========================================================================
  // Vault Operations
  // ===========================================================================

  /**
   * Create a new vault with encrypted credentials
   *
   * @param credentials - The accounting credentials to store
   * @param pin - User-provided PIN for encryption
   * @throws AccountingError if operation fails
   */
  static async createVault(credentials: AccountingCredentials, pin: string): Promise<void> {
    // Validate inputs
    if (!credentials.url || !credentials.email || !credentials.password) {
      throw new AccountingStorageError({
        type: 'VALIDATION_ERROR',
        message: 'All credential fields are required.'
      });
    }

    if (!pin || pin.length < 6) {
      throw new AccountingStorageError({
        type: 'VALIDATION_ERROR',
        message: 'PIN must be at least 6 characters.',
        field: 'pin'
      });
    }

    try {
      // Encrypt credentials
      const plaintext = JSON.stringify(credentials);
      const vault = await encrypt(plaintext, pin);

      // Store encrypted vault in localStorage
      const serialized = serializeVault(vault);
      const stored = setLocalStorage(STORAGE_KEYS.VAULT, serialized);

      if (!stored) {
        throw new AccountingStorageError({
          type: 'STORAGE_UNAVAILABLE',
          message: 'Failed to save vault. Browser storage may be full or disabled.'
        });
      }

      // Store decrypted credentials in sessionStorage for immediate use
      setSessionStorage(STORAGE_KEYS.SESSION, plaintext);

      // Update activity timestamp
      this.updateActivity();

      // Reset any rate limiting
      this.resetAttempts();
    } catch (error) {
      if (error instanceof AccountingStorageError) {
        throw error;
      }
      throw toAccountingError(error);
    }
  }

  /**
   * Unlock vault with PIN and store credentials in session
   *
   * @param pin - User-provided PIN for decryption
   * @returns Decrypted credentials
   * @throws AccountingError if operation fails or PIN is wrong
   */
  static async unlock(pin: string): Promise<AccountingCredentials> {
    // Check rate limiting
    const rateLimit = this.checkRateLimit();
    if (!rateLimit.allowed) {
      throw new AccountingStorageError({
        type: 'RATE_LIMITED',
        message: `Too many attempts. Please wait ${String(rateLimit.waitTime)} seconds.`,
        waitTime: rateLimit.waitTime
      });
    }

    // Get encrypted vault
    const vaultJson = getLocalStorage(STORAGE_KEYS.VAULT);
    if (!vaultJson) {
      throw new AccountingStorageError({
        type: 'VAULT_CORRUPTED',
        message: 'No vault found. Please set up your payment credentials.'
      });
    }

    try {
      // Parse vault
      const vault = parseVault(vaultJson);

      // Decrypt
      const plaintext = await decrypt(vault, pin);

      // Parse credentials
      const credentials = JSON.parse(plaintext) as AccountingCredentials;

      // Validate structure
      if (!credentials.url || !credentials.email || !credentials.password) {
        throw new VaultCorruptedError('Decrypted data has invalid structure');
      }

      // Store in sessionStorage
      setSessionStorage(STORAGE_KEYS.SESSION, plaintext);

      // Update activity
      this.updateActivity();

      // Record successful attempt (resets counter)
      this.recordSuccessfulAttempt();

      return credentials;
    } catch (error) {
      // Record failed attempt
      this.recordFailedAttempt();

      if (error instanceof AccountingStorageError) {
        throw error;
      }
      throw toAccountingError(error);
    }
  }

  /**
   * Lock vault (clear sessionStorage credentials)
   */
  static lock(): void {
    removeSessionStorage(STORAGE_KEYS.SESSION);
    removeSessionStorage(STORAGE_KEYS.ACTIVITY);
    // Keep rate limiting data in case of brute force after lock
  }

  /**
   * Delete vault entirely (both localStorage and sessionStorage)
   */
  static deleteVault(): void {
    removeLocalStorage(STORAGE_KEYS.VAULT);
    removeSessionStorage(STORAGE_KEYS.SESSION);
    removeSessionStorage(STORAGE_KEYS.ATTEMPTS);
    removeSessionStorage(STORAGE_KEYS.LAST_ATTEMPT);
    removeSessionStorage(STORAGE_KEYS.ACTIVITY);
  }

  /**
   * Update vault with new credentials (requires current PIN)
   *
   * @param credentials - New credentials to store
   * @param currentPin - Current PIN to verify ownership
   * @param newPin - Optional new PIN (uses currentPin if not provided)
   */
  static async updateVault(
    credentials: AccountingCredentials,
    currentPin: string,
    newPin?: string
  ): Promise<void> {
    // First verify the current PIN by attempting to unlock
    await this.unlock(currentPin);

    // Create new vault with new or same PIN
    await this.createVault(credentials, newPin ?? currentPin);
  }

  // ===========================================================================
  // Credential Access
  // ===========================================================================

  /**
   * Get decrypted credentials from sessionStorage (if unlocked)
   *
   * @returns Credentials if unlocked, null otherwise
   */
  static getCredentials(): AccountingCredentials | null {
    const session = getSessionStorage(STORAGE_KEYS.SESSION);
    if (!session) {
      return null;
    }

    try {
      const credentials = JSON.parse(session) as AccountingCredentials;
      if (!credentials.url || !credentials.email || !credentials.password) {
        return null;
      }
      return credentials;
    } catch {
      return null;
    }
  }

  // ===========================================================================
  // Rate Limiting
  // ===========================================================================

  /**
   * Check if unlock attempt is allowed
   *
   * @returns Object with allowed flag and wait time in seconds
   */
  static checkRateLimit(): { allowed: boolean; waitTime: number } {
    const attempts = this.getAttemptCount();
    const lastAttempt = this.getLastAttemptTime();

    // Determine required delay based on attempt count
    const delayIndex = Math.min(attempts, RATE_LIMIT_DELAYS.length - 1);
    const requiredDelay = RATE_LIMIT_DELAYS[delayIndex] ?? 0;

    // If no delay required, allow
    if (requiredDelay === 0) {
      return { allowed: true, waitTime: 0 };
    }

    // Calculate time since last attempt
    const now = Date.now();
    const elapsed = lastAttempt ? (now - lastAttempt) / 1000 : Infinity;

    if (elapsed >= requiredDelay) {
      return { allowed: true, waitTime: 0 };
    }

    return {
      allowed: false,
      waitTime: Math.ceil(requiredDelay - elapsed)
    };
  }

  /**
   * Record a successful unlock attempt (resets counter)
   */
  static recordSuccessfulAttempt(): void {
    this.resetAttempts();
  }

  /**
   * Record a failed unlock attempt (increments counter)
   */
  static recordFailedAttempt(): void {
    const attempts = this.getAttemptCount();
    setSessionStorage(STORAGE_KEYS.ATTEMPTS, String(attempts + 1));
    setSessionStorage(STORAGE_KEYS.LAST_ATTEMPT, String(Date.now()));
  }

  /**
   * Reset attempt counter (after successful unlock)
   */
  static resetAttempts(): void {
    removeSessionStorage(STORAGE_KEYS.ATTEMPTS);
    removeSessionStorage(STORAGE_KEYS.LAST_ATTEMPT);
  }

  /**
   * Get current attempt count
   */
  private static getAttemptCount(): number {
    const attempts = getSessionStorage(STORAGE_KEYS.ATTEMPTS);
    return attempts ? Number.parseInt(attempts, 10) || 0 : 0;
  }

  /**
   * Get timestamp of last attempt
   */
  private static getLastAttemptTime(): number | null {
    const lastAttempt = getSessionStorage(STORAGE_KEYS.LAST_ATTEMPT);
    return lastAttempt ? Number.parseInt(lastAttempt, 10) || null : null;
  }

  // ===========================================================================
  // Auto-Lock
  // ===========================================================================

  /**
   * Update last activity timestamp
   */
  static updateActivity(): void {
    setSessionStorage(STORAGE_KEYS.ACTIVITY, String(Date.now()));
  }

  /**
   * Get last activity timestamp
   */
  static getLastActivity(): number | null {
    const activity = getSessionStorage(STORAGE_KEYS.ACTIVITY);
    return activity ? Number.parseInt(activity, 10) || null : null;
  }

  /**
   * Check if auto-lock should trigger and lock if needed
   *
   * @param timeoutMinutes - Inactivity timeout in minutes (default: 15)
   * @returns true if vault was auto-locked
   */
  static checkAutoLock(timeoutMinutes: number = DEFAULT_AUTO_LOCK_TIMEOUT): boolean {
    // Only check if unlocked
    if (!this.isUnlocked()) {
      return false;
    }

    const lastActivity = this.getLastActivity();
    if (!lastActivity) {
      // No activity recorded, lock for safety
      this.lock();
      return true;
    }

    const elapsed = Date.now() - lastActivity;
    const timeoutMs = timeoutMinutes * 60 * 1000;

    if (elapsed > timeoutMs) {
      this.lock();
      return true;
    }

    return false;
  }
}

// =============================================================================
// Exports
// =============================================================================

export { STORAGE_KEYS, DEFAULT_AUTO_LOCK_TIMEOUT };
