/**
 * crypto.ts — identity-keyed crypto for direct peer-to-peer agent sessions
 * (tunnel protocol v2).
 *
 * It mirrors the Go SessionCipher in
 * `sdk/golang/syfthubapi/transport/crypto_session.go` so a browser client and
 * a syfthubapi host derive identical AES-256-GCM keys:
 *
 *   shared   = X25519(my_identity_priv, peer_identity_pub)
 *   req_key  = HKDF-SHA256(shared, salt=session_id, info="syfthub-agent-request-v2")
 *   resp_key = HKDF-SHA256(shared, salt=session_id, info="syfthub-agent-response-v2")
 *   per message: AES-256-GCM, fresh random 12-byte nonce, AAD = correlation_id
 *
 * The identity-pair shared secret is stable, so the session id is the HKDF
 * salt that makes every session's keys unique. The scheme is symmetric: the
 * client encrypts requests / decrypts responses; the host does the inverse.
 *
 * SECURITY NOTE: static-static ECDH has no forward secrecy (design decision
 * D1). The browser holds no long-term key — it uses a fresh per-session
 * ephemeral identity keypair — so in practice each web session is independent.
 * See syfthub-desktop/docs/p2p-agent-direct-nats-design.md.
 */
import { gcm } from '@noble/ciphers/aes';
import { x25519 } from '@noble/curves/ed25519';
import { hkdf } from '@noble/hashes/hkdf';
import { sha256 } from '@noble/hashes/sha256';

/** AES-256-GCM nonce length — matches `nonceSize` in the Go transport. */
const NONCE_SIZE = 12;

/** HKDF domain-separation labels — must byte-match the Go v2 labels. */
const REQUEST_INFO = 'syfthub-agent-request-v2';
const RESPONSE_INFO = 'syfthub-agent-response-v2';

const utf8 = new TextEncoder();

/**
 * Encode raw bytes as unpadded base64url. Matches Go's `base64.RawURLEncoding`,
 * which the transport uses for every nonce / ciphertext / public key.
 */
export function b64urlEncode(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** Decode a base64url string (with or without padding) to raw bytes. */
export function b64urlDecode(value: string): Uint8Array {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    out[i] = binary.charCodeAt(i);
  }
  return out;
}

/** An X25519 keypair; the browser generates a fresh one per agent session. */
export interface IdentityKeyPair {
  privateKey: Uint8Array;
  publicKey: Uint8Array;
}

/** Generate a fresh X25519 identity keypair. */
export function generateIdentityKeyPair(): IdentityKeyPair {
  const privateKey = x25519.utils.randomPrivateKey();
  const publicKey = x25519.getPublicKey(privateKey);
  return { privateKey, publicKey };
}

/**
 * SessionCipher holds the AES-256-GCM keys for both directions of one agent
 * session. ECDH is commutative, so both peers derive identical keys.
 */
export class SessionCipher {
  private readonly requestKey: Uint8Array;
  private readonly responseKey: Uint8Array;

  /**
   * @param identityPrivateKey - this peer's X25519 private key (raw 32 bytes)
   * @param peerPublicKeyB64 - the remote peer's X25519 public key (base64url)
   * @param sessionId - the session id, used as the HKDF salt
   */
  constructor(identityPrivateKey: Uint8Array, peerPublicKeyB64: string, sessionId: string) {
    if (!sessionId) {
      throw new Error('session id is empty');
    }
    const peerPublicKey = b64urlDecode(peerPublicKeyB64);
    const shared = x25519.getSharedSecret(identityPrivateKey, peerPublicKey);
    const salt = utf8.encode(sessionId);
    this.requestKey = hkdf(sha256, shared, salt, utf8.encode(REQUEST_INFO), 32);
    this.responseKey = hkdf(sha256, shared, salt, utf8.encode(RESPONSE_INFO), 32);
  }

  /** Encrypt a client to host message. correlationId is bound as GCM AAD. */
  encryptRequest(
    plaintext: Uint8Array,
    correlationId: string
  ): { nonce: string; ciphertext: string } {
    return seal(this.requestKey, plaintext, correlationId);
  }

  /** Decrypt a host to client message (agent_event). */
  decryptResponse(nonceB64: string, ciphertextB64: string, correlationId: string): Uint8Array {
    const nonce = b64urlDecode(nonceB64);
    if (nonce.length !== NONCE_SIZE) {
      throw new Error(`nonce must be ${NONCE_SIZE} bytes, got ${nonce.length}`);
    }
    const aad = utf8.encode(correlationId);
    return gcm(this.responseKey, nonce, aad).decrypt(b64urlDecode(ciphertextB64));
  }
}

/** Encrypt under a fresh random nonce; returns base64url nonce + ciphertext. */
function seal(
  key: Uint8Array,
  plaintext: Uint8Array,
  correlationId: string
): { nonce: string; ciphertext: string } {
  const nonce = crypto.getRandomValues(new Uint8Array(NONCE_SIZE));
  const aad = utf8.encode(correlationId);
  const ciphertext = gcm(key, nonce, aad).encrypt(plaintext);
  return { nonce: b64urlEncode(nonce), ciphertext: b64urlEncode(ciphertext) };
}
