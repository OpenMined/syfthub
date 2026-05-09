/**
 * Stubs for the on-chain payment wallet.
 *
 * Unit 12 of the transaction-policy batch ships the real Tempo-wallet hook
 * (`useTempoWallet`), the WWW-Authenticate parser (`parseChallenge`), and
 * the credential signer (`signCredentialViaTempo`). Until that lands, this
 * unit (#13) can't import them — so we define minimal stand-ins here. They
 * are exported under stable names so the modal's call sites don't have to
 * change when unit 12 is merged: that PR just removes this file and re-
 * exports from the real modules.
 *
 * The shapes here intentionally mirror what unit 12's design proposes so
 * the swap is mechanical.
 */

// =============================================================================
// Challenge parsing
// =============================================================================

export interface ParsedChallenge {
  id: string;
  realm: string;
  method: string;
  intent: string;
  request: string;
  expires: string;
  amount: string;
  currency: `0x${string}`;
  recipient: `0x${string}`;
}

const PAYMENT_PREFIX_RE = /^Payment\s+/i;

/**
 * Best-effort `WWW-Authenticate: Payment ...` parser. Mirrors the v1 spec
 * shape (`id, realm, method, intent, request, expires`) so the modal can
 * surface a sane parsed view even without unit 12 present.
 */
export function parseChallenge(wwwAuthenticate: string): ParsedChallenge {
  const trimmed = wwwAuthenticate.trim();
  if (!PAYMENT_PREFIX_RE.test(trimmed)) {
    throw new Error('Not a Payment challenge: missing "Payment " prefix');
  }
  const body = trimmed.replace(PAYMENT_PREFIX_RE, '');
  const params = parseAuthParams(body);
  return {
    id: params.id ?? '',
    realm: params.realm ?? '',
    method: params.method ?? 'tempo',
    intent: params.intent ?? 'charge',
    request: params.request ?? '',
    expires: params.expires ?? '',
    amount: params.amount ?? '0',
    currency: (params.currency ?? '0x0000000000000000000000000000000000000000') as `0x${string}`,
    recipient: (params.recipient ?? '0x0000000000000000000000000000000000000000') as `0x${string}`
  };
}

/**
 * Hand-rolled `key="value", key2="value2"` parser. Single linear pass,
 * no backtracking — safe on adversarial input. Mirrors the lenient form
 * unit 12's real parser uses for forward compatibility.
 */
function parseAuthParams(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  let i = 0;
  while (i < body.length) {
    while (i < body.length && (body[i] === ' ' || body[i] === ',')) i += 1;
    if (i >= body.length) break;
    const keyStart = i;
    while (i < body.length && body[i] !== '=' && body[i] !== ' ') i += 1;
    const key = body.slice(keyStart, i);
    while (i < body.length && body[i] !== '=') i += 1;
    if (i >= body.length) break;
    i += 1; // skip '='
    while (i < body.length && body[i] === ' ') i += 1;
    let value: string;
    if (body[i] === '"') {
      i += 1;
      const valueStart = i;
      while (i < body.length && body[i] !== '"') {
        i += body[i] === '\\' && i + 1 < body.length ? 2 : 1;
      }
      value = body.slice(valueStart, i).replaceAll(String.raw`\"`, '"');
      if (i < body.length) i += 1;
    } else {
      const valueStart = i;
      while (i < body.length && body[i] !== ',') i += 1;
      value = body.slice(valueStart, i).trim();
    }
    if (key) out[key] = value;
  }
  return out;
}

// =============================================================================
// Wallet hook contract
// =============================================================================

export interface SignedCredential {
  credential: string;
  txHash: `0x${string}`;
}

export interface PaymentWallet {
  address: string | null;
  hasWallet: boolean;
  isUnlocked: boolean;
  unlockWallet: (passphrase: string) => Promise<void>;
  signCredential: (
    challenge: ParsedChallenge,
    options: { rpcUrl: string; chainId: number; decimals?: number }
  ) => Promise<SignedCredential>;
}

/**
 * Default stub: a wallet that says "no wallet configured" and refuses to
 * sign. The real implementation lives in unit 12. Tests inject a fake.
 */
export function useWalletForPayments(): PaymentWallet {
  return {
    address: null,
    hasWallet: false,
    isUnlocked: false,
    unlockWallet: () => Promise.reject(new Error('Wallet support not yet available (unit 12)')),
    signCredential: () => Promise.reject(new Error('Wallet support not yet available (unit 12)'))
  };
}
