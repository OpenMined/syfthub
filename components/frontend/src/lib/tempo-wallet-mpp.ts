/**
 * Tempo Wallet — MPP (Micro Payment Protocol) Helpers
 *
 * Pure functions for parsing `WWW-Authenticate: Payment ...` challenges
 * emitted by the aggregator and producing signed `Payment <base64...>`
 * credentials backed by an on-chain Tempo ERC-20 transfer.
 *
 * See: PUBSUB.md / mpp_demo for the wire-format specification.
 */

import {
  createPublicClient,
  createWalletClient,
  defineChain,
  encodeFunctionData,
  erc20Abi,
  http
} from 'viem';
import { privateKeyToAccount } from 'viem/accounts';

import { privateKeyToHex } from './tempo-wallet-crypto';

// =============================================================================
// Types
// =============================================================================

export interface ParsedChallenge {
  /** Challenge id (echoed back in the credential). */
  id: string;
  realm: string;
  method: string;
  intent: string;
  /** Raw base64url-encoded request body, echoed back verbatim. */
  request: string;
  /** ISO-8601 timestamp string. */
  expires: string;
  /** Decoded amount, as a decimal string (e.g. "0.10"). */
  amount: string;
  /** ERC-20 token contract address (0x-prefixed). */
  currency: `0x${string}`;
  /** Recipient address for the transfer (0x-prefixed). */
  recipient: `0x${string}`;
}

export interface SignedCredential {
  /** Full `Authorization` header value: `Payment <base64url-json>`. */
  credential: string;
  /** Tempo transaction hash (0x-prefixed, 32 bytes hex). */
  txHash: `0x${string}`;
}

// =============================================================================
// Base64url helpers
// =============================================================================

function base64UrlDecode(input: string): string {
  const pad = (4 - (input.length % 4)) % 4;
  const b64 = input.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat(pad);
  return globalThis.atob(b64);
}

function base64UrlEncode(input: string): string {
  return globalThis.btoa(input).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
}

interface ChallengeRequestPayload {
  amount: string | number;
  currency: string;
  recipient: string;
}

// =============================================================================
// parseChallenge
// =============================================================================

const PAYMENT_PREFIX_RE = /^Payment\s+/i;

/**
 * Parses a `WWW-Authenticate: Payment ...` header value into a ParsedChallenge.
 *
 * Expected format:
 *   `Payment id="abc", realm="x", method="tempo", intent="charge",
 *           request="<base64url-json>", expires="2026-01-01T00:00:00Z"`
 *
 * Whitespace and ordering of keys is not significant; quoted values may
 * contain commas.
 */
export function parseChallenge(wwwAuthenticate: string): ParsedChallenge {
  const trimmed = wwwAuthenticate.trim();
  if (!PAYMENT_PREFIX_RE.test(trimmed)) {
    throw new Error('Not a Payment challenge: missing "Payment " prefix');
  }
  const body = trimmed.replace(PAYMENT_PREFIX_RE, '');
  const params = parseAuthParams(body);

  const id = requireParameter(params, 'id');
  const realm = requireParameter(params, 'realm');
  const method = requireParameter(params, 'method');
  const intent = requireParameter(params, 'intent');
  const request = requireParameter(params, 'request');
  const expires = requireParameter(params, 'expires');

  let payload: ChallengeRequestPayload;
  try {
    const decoded = base64UrlDecode(request);
    payload = JSON.parse(decoded) as ChallengeRequestPayload;
  } catch (error) {
    throw new Error(
      `Payment challenge has invalid base64url JSON in request: ${
        error instanceof Error ? error.message : String(error)
      }`
    );
  }

  if (typeof payload.currency !== 'string' || typeof payload.recipient !== 'string') {
    throw new TypeError('Payment challenge request missing currency or recipient');
  }
  if (typeof payload.amount !== 'string' && typeof payload.amount !== 'number') {
    throw new TypeError('Payment challenge request missing amount');
  }

  return {
    id,
    realm,
    method,
    intent,
    request,
    expires,
    amount: String(payload.amount),
    currency: payload.currency as `0x${string}`,
    recipient: payload.recipient as `0x${string}`
  };
}

function requireParameter(params: Record<string, string>, key: string): string {
  const v = params[key];
  if (v === undefined) {
    throw new Error(`Payment challenge missing required parameter: ${key}`);
  }
  return v;
}

// Matches `key = "quoted value"` or `key = unquoted` in an RFC 7235-ish
// comma-separated parameter list. Both alternatives use non-overlapping
// character classes so a given input position can only match one branch —
// this keeps matching linear (no super-linear backtracking).
// eslint-disable-next-line sonarjs/slow-regex -- alternatives are non-overlapping; bounded input
const AUTH_PARAM_RE = /([A-Za-z0-9_-]+)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^",]*))/g;

function parseAuthParams(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const match of body.matchAll(AUTH_PARAM_RE)) {
    const key = match[1];
    if (!key) continue;
    const quoted = match[2];
    const unquoted = match[3];
    if (quoted !== undefined) {
      out[key] = quoted.replaceAll(String.raw`\"`, '"').replaceAll('\\\\', '\\');
    } else if (unquoted !== undefined) {
      out[key] = unquoted.trim();
    }
  }
  return out;
}

// =============================================================================
// Credential building
// =============================================================================

interface CredentialBody {
  challenge: {
    id: string;
    realm: string;
    method: string;
    intent: string;
    request: string;
    expires: string;
  };
  payload: {
    type: 'transaction';
    signature: string;
  };
  source: string;
}

/**
 * Builds the final `Payment <base64url(json)>` credential string given a
 * Tempo transaction hash and the signer address. Pure / synchronous —
 * separated for testability.
 */
export function buildCredential(options: {
  challenge: ParsedChallenge;
  txHash: `0x${string}`;
  signerAddress: `0x${string}`;
  chainId: number;
}): string {
  const body: CredentialBody = {
    challenge: {
      id: options.challenge.id,
      realm: options.challenge.realm,
      method: options.challenge.method,
      intent: options.challenge.intent,
      request: options.challenge.request,
      expires: options.challenge.expires
    },
    payload: { type: 'transaction', signature: options.txHash },
    source: `did:pkh:eip155:${String(options.chainId)}:${options.signerAddress}`
  };
  return `Payment ${base64UrlEncode(JSON.stringify(body))}`;
}

// =============================================================================
// Amount handling
// =============================================================================

/**
 * Converts a decimal-string amount (e.g. "0.10") into a bigint of the smallest
 * token unit using the supplied decimals. Avoids floating-point.
 */
export function parseTokenAmount(amount: string, decimals: number): bigint {
  const trimmed = amount.trim();
  if (!/^-?\d+(\.\d+)?$/.test(trimmed)) {
    throw new Error(`Invalid amount: ${amount}`);
  }
  const negative = trimmed.startsWith('-');
  const unsigned = negative ? trimmed.slice(1) : trimmed;
  const dotIndex = unsigned.indexOf('.');
  const intPart = dotIndex === -1 ? unsigned : unsigned.slice(0, dotIndex);
  const fracPart = dotIndex === -1 ? '' : unsigned.slice(dotIndex + 1);
  if (fracPart.length > decimals) {
    throw new Error(`Amount has more than ${String(decimals)} fractional digits`);
  }
  const padded = fracPart.padEnd(decimals, '0');
  const raw = BigInt(intPart + padded);
  return negative ? -raw : raw;
}

// =============================================================================
// On-chain signing & broadcast
// =============================================================================

function tempoChain(chainId: number, rpcUrl: string) {
  return defineChain({
    id: chainId,
    name: 'Tempo',
    nativeCurrency: { name: 'Tempo Gas', symbol: 'TEMPO', decimals: 18 },
    rpcUrls: { default: { http: [rpcUrl] } }
  });
}

/**
 * Builds an ERC-20 transfer, signs it with the wallet's private key, broadcasts
 * it via the configured Tempo RPC, and returns the credential string + tx hash.
 */
export async function signCredentialViaTempo(options: {
  challenge: ParsedChallenge;
  privateKey: Uint8Array;
  rpcUrl: string;
  chainId: number;
  /** ERC-20 decimals for the currency. PathUSD = 6 by default. */
  decimals?: number;
}): Promise<SignedCredential> {
  const decimals = options.decimals ?? 6;
  const account = privateKeyToAccount(privateKeyToHex(options.privateKey));
  const chain = tempoChain(options.chainId, options.rpcUrl);

  const wallet = createWalletClient({ account, chain, transport: http(options.rpcUrl) });
  const value = parseTokenAmount(options.challenge.amount, decimals);
  const data = encodeFunctionData({
    abi: erc20Abi,
    functionName: 'transfer',
    args: [options.challenge.recipient, value]
  });

  const txHash = await wallet.sendTransaction({
    to: options.challenge.currency,
    data,
    value: 0n
  });

  return {
    credential: buildCredential({
      challenge: options.challenge,
      txHash,
      signerAddress: account.address,
      chainId: options.chainId
    }),
    txHash
  };
}

/**
 * Reads the ERC-20 balance for the wallet at the given currency contract.
 * Returns the raw bigint (caller formats for display).
 */
export async function readErc20Balance(options: {
  address: `0x${string}`;
  rpcUrl: string;
  chainId: number;
  currency: `0x${string}`;
}): Promise<bigint> {
  const client = createPublicClient({
    chain: tempoChain(options.chainId, options.rpcUrl),
    transport: http(options.rpcUrl)
  });
  return client.readContract({
    address: options.currency,
    abi: erc20Abi,
    functionName: 'balanceOf',
    args: [options.address]
  });
}
