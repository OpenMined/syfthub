/**
 * Tempo Wallet — Pure Crypto Helpers
 *
 * Passphrase-encrypted private key persistence for the browser-local Tempo
 * payment wallet (transaction policy unit 12).
 *
 * Encryption scheme:
 *   passphrase --PBKDF2(SHA-256, 100k iters)--> 256-bit key
 *   key + 12-byte nonce + private key --AES-256-GCM--> ciphertext
 *   stored blob = base64(salt | nonce | ciphertext+tag)
 *
 * SECURITY: This module never logs or returns the raw passphrase or derived
 * key. Callers MUST treat the decrypted private key bytes as sensitive — wipe
 * them from memory ASAP and never serialize them.
 */

import { privateKeyToAddress as viemPrivateKeyToAddress } from 'viem/accounts';

const PBKDF2_ITERATIONS = 100_000;
const SALT_LENGTH = 16;
const NONCE_LENGTH = 12;
const KEY_LENGTH_BITS = 256;
const PRIVATE_KEY_LENGTH = 32;

// =============================================================================
// Base64 helpers (url-safe + standard)
// =============================================================================

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCodePoint(byte);
  }
  return globalThis.btoa(binary);
}

function base64ToBytes(b64: string): Uint8Array {
  const binary = globalThis.atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.codePointAt(index) ?? 0;
  }
  return bytes;
}

// =============================================================================
// Crypto primitives
// =============================================================================

export async function deriveKey(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const enc = new TextEncoder();
  const baseKey = await globalThis.crypto.subtle.importKey(
    'raw',
    enc.encode(passphrase),
    'PBKDF2',
    false,
    ['deriveKey']
  );
  return globalThis.crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: salt as unknown as BufferSource,
      iterations: PBKDF2_ITERATIONS,
      hash: 'SHA-256'
    },
    baseKey,
    { name: 'AES-GCM', length: KEY_LENGTH_BITS },
    false,
    ['encrypt', 'decrypt']
  );
}

/**
 * Encrypts a private key with a passphrase.
 * @returns Base64-encoded blob: `salt(16) | nonce(12) | ciphertext+tag`.
 */
export async function encryptPrivateKey(
  privateKey: Uint8Array,
  passphrase: string
): Promise<string> {
  if (privateKey.length !== PRIVATE_KEY_LENGTH) {
    throw new Error(`Private key must be ${String(PRIVATE_KEY_LENGTH)} bytes`);
  }
  const salt = globalThis.crypto.getRandomValues(new Uint8Array(SALT_LENGTH));
  const nonce = globalThis.crypto.getRandomValues(new Uint8Array(NONCE_LENGTH));
  const key = await deriveKey(passphrase, salt);
  const ciphertext = new Uint8Array(
    await globalThis.crypto.subtle.encrypt(
      { name: 'AES-GCM', iv: nonce as unknown as BufferSource },
      key,
      privateKey as unknown as BufferSource
    )
  );
  const blob = new Uint8Array(salt.length + nonce.length + ciphertext.length);
  blob.set(salt, 0);
  blob.set(nonce, salt.length);
  blob.set(ciphertext, salt.length + nonce.length);
  return bytesToBase64(blob);
}

/**
 * Decrypts a previously encrypted private key. Throws on wrong passphrase
 * (GCM auth tag mismatch).
 */
export async function decryptPrivateKey(blob: string, passphrase: string): Promise<Uint8Array> {
  const bytes = base64ToBytes(blob);
  if (bytes.length < SALT_LENGTH + NONCE_LENGTH + PRIVATE_KEY_LENGTH) {
    throw new Error('Encrypted blob is too short');
  }
  const salt = bytes.slice(0, SALT_LENGTH);
  const nonce = bytes.slice(SALT_LENGTH, SALT_LENGTH + NONCE_LENGTH);
  const ciphertext = bytes.slice(SALT_LENGTH + NONCE_LENGTH);
  const key = await deriveKey(passphrase, salt);
  const plaintext = await globalThis.crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: nonce as unknown as BufferSource },
    key,
    ciphertext as unknown as BufferSource
  );
  return new Uint8Array(plaintext);
}

/**
 * Generates a 32-byte cryptographically random private key.
 * Note: viem expects keys < secp256k1 curve order, but the probability of
 * collision/overflow with random 32 bytes is astronomically low.
 */
export function generatePrivateKey(): Uint8Array {
  return globalThis.crypto.getRandomValues(new Uint8Array(PRIVATE_KEY_LENGTH));
}

/** Encodes raw private key bytes as a 0x-prefixed hex string (viem format). */
export function privateKeyToHex(privateKey: Uint8Array): `0x${string}` {
  if (privateKey.length !== PRIVATE_KEY_LENGTH) {
    throw new Error(`Private key must be ${String(PRIVATE_KEY_LENGTH)} bytes`);
  }
  let hex = '';
  for (const byte of privateKey) {
    hex += byte.toString(16).padStart(2, '0');
  }
  return `0x${hex}`;
}

/** Derives the EVM address (0x-prefixed, EIP-55 checksummed) from a private key. */
export function privateKeyToAddress(privateKey: Uint8Array): `0x${string}` {
  return viemPrivateKeyToAddress(privateKeyToHex(privateKey));
}
