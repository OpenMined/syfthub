/**
 * Crypto Vault Module
 *
 * Provides secure encryption/decryption for sensitive credentials using
 * the Web Crypto API with AES-256-GCM encryption and PBKDF2 key derivation.
 *
 * Security Properties:
 * - AES-256-GCM provides authenticated encryption (integrity + confidentiality)
 * - PBKDF2 with 310,000 iterations (OWASP 2023 recommendation)
 * - Fresh random salt and IV for each encryption
 * - Non-extractable keys (can't be stolen by XSS)
 */

// =============================================================================
// Constants
// =============================================================================

/** PBKDF2 iterations - OWASP 2023 recommendation for SHA-256 */
const PBKDF2_ITERATIONS = 310_000;

/** AES key length in bits */
const KEY_LENGTH = 256;

/** GCM initialization vector length in bytes (96 bits is optimal for GCM) */
const IV_LENGTH = 12;

/** PBKDF2 salt length in bytes */
const SALT_LENGTH = 16;

/** Current vault schema version for future migrations */
export const VAULT_VERSION = 1;

// =============================================================================
// Types
// =============================================================================

/**
 * Encrypted vault structure stored in localStorage
 */
export interface EncryptedVault {
  /** Base64-encoded AES-GCM ciphertext (includes auth tag) */
  ciphertext: string;
  /** Base64-encoded initialization vector (12 bytes) */
  iv: string;
  /** Base64-encoded PBKDF2 salt (16 bytes) */
  salt: string;
  /** Schema version for future migrations */
  version: number;
}

// =============================================================================
// Custom Errors
// =============================================================================

/**
 * Thrown when decryption fails due to incorrect PIN
 * (AES-GCM authentication tag verification failure)
 */
export class InvalidPinError extends Error {
  constructor(message = 'Invalid PIN') {
    super(message);
    this.name = 'InvalidPinError';
    Object.setPrototypeOf(this, InvalidPinError.prototype);
  }
}

/**
 * Thrown when Web Crypto API is not available
 */
export class CryptoNotSupportedError extends Error {
  constructor(message = 'Web Crypto API is not supported in this browser') {
    super(message);
    this.name = 'CryptoNotSupportedError';
    Object.setPrototypeOf(this, CryptoNotSupportedError.prototype);
  }
}

/**
 * Thrown when vault data is malformed or corrupted
 */
export class VaultCorruptedError extends Error {
  constructor(message = 'Vault data is corrupted or invalid') {
    super(message);
    this.name = 'VaultCorruptedError';
    Object.setPrototypeOf(this, VaultCorruptedError.prototype);
  }
}

// =============================================================================
// Utility Functions (Internal)
// =============================================================================

/**
 * Encode ArrayBuffer or Uint8Array to Base64 string
 */
function base64Encode(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = '';
  for (let index = 0; index < bytes.byteLength; index++) {
    const byte = bytes[index];
    if (byte !== undefined) {
      binary += String.fromCodePoint(byte);
    }
  }
  return btoa(binary);
}

/**
 * Decode Base64 string to Uint8Array
 */
function base64Decode(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index++) {
    bytes[index] = binary.codePointAt(index) ?? 0;
  }
  return bytes;
}

/**
 * Generate cryptographically secure random salt
 */
function generateSalt(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(SALT_LENGTH));
}

/**
 * Generate cryptographically secure random IV
 */
function generateIV(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(IV_LENGTH));
}

/**
 * Derive AES-256-GCM key from PIN using PBKDF2
 */
async function deriveKeyFromPin(pin: string, salt: Uint8Array): Promise<CryptoKey> {
  const encoder = new TextEncoder();

  // Import PIN as raw key material for PBKDF2
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    encoder.encode(pin),
    'PBKDF2',
    false, // not extractable
    ['deriveKey']
  );

  // Derive AES-GCM key using PBKDF2
  // Use salt.buffer to get ArrayBuffer from Uint8Array
  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: salt.buffer as ArrayBuffer,
      iterations: PBKDF2_ITERATIONS,
      hash: 'SHA-256'
    },
    keyMaterial,
    { name: 'AES-GCM', length: KEY_LENGTH },
    false, // not extractable - key can never be read by JS
    ['encrypt', 'decrypt']
  );
}

/**
 * Validate vault structure before decryption
 */
function validateVaultStructure(vault: unknown): vault is EncryptedVault {
  if (!vault || typeof vault !== 'object') {
    return false;
  }

  const v = vault as Record<string, unknown>;

  return (
    typeof v.ciphertext === 'string' &&
    typeof v.iv === 'string' &&
    typeof v.salt === 'string' &&
    typeof v.version === 'number' &&
    v.ciphertext.length > 0 &&
    v.iv.length > 0 &&
    v.salt.length > 0
  );
}

// =============================================================================
// Public API
// =============================================================================

/**
 * Check if Web Crypto API is supported in the current environment
 */
export function isCryptoSupported(): boolean {
  try {
    // Check for crypto global and its methods
    if (typeof crypto === 'undefined' || !crypto.subtle) {
      return false;
    }
    return (
      typeof crypto.getRandomValues === 'function' &&
      typeof crypto.subtle.importKey === 'function' &&
      typeof crypto.subtle.deriveKey === 'function' &&
      typeof crypto.subtle.encrypt === 'function' &&
      typeof crypto.subtle.decrypt === 'function'
    );
  } catch {
    return false;
  }
}

/**
 * Encrypt plaintext with a PIN
 *
 * @param plaintext - The string to encrypt
 * @param pin - User-provided PIN for key derivation
 * @returns Encrypted vault object ready for storage
 * @throws {CryptoNotSupportedError} If Web Crypto API is unavailable
 */
export async function encrypt(plaintext: string, pin: string): Promise<EncryptedVault> {
  if (!isCryptoSupported()) {
    throw new CryptoNotSupportedError();
  }

  // Generate fresh random values for each encryption
  const salt = generateSalt();
  const iv = generateIV();

  // Derive encryption key from PIN
  const key = await deriveKeyFromPin(pin, salt);

  // Encrypt the plaintext
  const encoder = new TextEncoder();
  const plaintextBuffer = encoder.encode(plaintext);

  const ciphertextBuffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: iv.buffer as ArrayBuffer },
    key,
    plaintextBuffer
  );

  // Return vault object with Base64-encoded values
  return {
    ciphertext: base64Encode(ciphertextBuffer),
    iv: base64Encode(iv),
    salt: base64Encode(salt),
    version: VAULT_VERSION
  };
}

/**
 * Decrypt an encrypted vault with a PIN
 *
 * @param vault - The encrypted vault object
 * @param pin - User-provided PIN for key derivation
 * @returns Decrypted plaintext string
 * @throws {CryptoNotSupportedError} If Web Crypto API is unavailable
 * @throws {VaultCorruptedError} If vault structure is invalid
 * @throws {InvalidPinError} If PIN is incorrect (authentication tag fails)
 */
export async function decrypt(vault: EncryptedVault, pin: string): Promise<string> {
  if (!isCryptoSupported()) {
    throw new CryptoNotSupportedError();
  }

  // Validate vault structure
  if (!validateVaultStructure(vault)) {
    throw new VaultCorruptedError('Invalid vault structure');
  }

  // Decode Base64 values
  let salt: Uint8Array;
  let iv: Uint8Array;
  let ciphertext: Uint8Array;

  try {
    salt = base64Decode(vault.salt);
    iv = base64Decode(vault.iv);
    ciphertext = base64Decode(vault.ciphertext);
  } catch {
    throw new VaultCorruptedError('Failed to decode vault data');
  }

  // Validate decoded lengths
  if (salt.length !== SALT_LENGTH) {
    throw new VaultCorruptedError(
      `Invalid salt length: expected ${SALT_LENGTH}, got ${salt.length}`
    );
  }
  if (iv.length !== IV_LENGTH) {
    throw new VaultCorruptedError(`Invalid IV length: expected ${IV_LENGTH}, got ${iv.length}`);
  }

  // Derive decryption key from PIN
  const key = await deriveKeyFromPin(pin, salt);

  // Decrypt the ciphertext
  try {
    const plaintextBuffer = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: iv.buffer as ArrayBuffer },
      key,
      ciphertext.buffer as ArrayBuffer
    );

    const decoder = new TextDecoder();
    return decoder.decode(plaintextBuffer);
  } catch (error) {
    // AES-GCM throws OperationError when authentication tag verification fails
    // This happens when the PIN is wrong or data is tampered
    if (error instanceof DOMException && error.name === 'OperationError') {
      throw new InvalidPinError('Incorrect PIN or corrupted vault');
    }
    throw error;
  }
}

/**
 * Parse a vault from JSON string (e.g., from localStorage)
 *
 * @param json - JSON string representation of vault
 * @returns Parsed and validated vault object
 * @throws {VaultCorruptedError} If JSON is invalid or structure is wrong
 */
export function parseVault(json: string): EncryptedVault {
  try {
    const parsed = JSON.parse(json);
    if (!validateVaultStructure(parsed)) {
      throw new VaultCorruptedError('Invalid vault structure');
    }
    return parsed;
  } catch (error) {
    if (error instanceof VaultCorruptedError) {
      throw error;
    }
    throw new VaultCorruptedError('Failed to parse vault JSON');
  }
}

/**
 * Serialize a vault to JSON string for storage
 *
 * @param vault - The vault object to serialize
 * @returns JSON string representation
 */
export function serializeVault(vault: EncryptedVault): string {
  return JSON.stringify(vault);
}
