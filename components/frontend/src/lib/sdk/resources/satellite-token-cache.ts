/**
 * Reuses satellite tokens instead of minting one per request.
 *
 * Held in memory only. Callers asking for the same key while a mint is in
 * flight share that one mint.
 */

/**
 * A token is reused only while it has at least this long to live.
 *
 * Sized for the slowest use: the aggregator calls the model after retrieval,
 * which may take 30 s.
 */
export const MIN_REMAINING_SECONDS = 40;

/** What a mint returns. A token with no lifetime is never reused. */
export interface MintedToken {
  targetToken: string;
  expiresIn?: number;
}

interface Entry {
  minted: Promise<unknown>;
  /** Epoch ms when the mint was requested. */
  requestedAt: number;
  /** Epoch ms; unset while the mint is in flight. */
  expiresAt?: number;
}

export class SatelliteTokenCache {
  private readonly entries = new Map<string, Entry>();

  /** @param now - Clock in epoch ms; replaceable in tests. */
  constructor(private readonly now: () => number = Date.now) {}

  /**
   * The token cached under `key`, or a new one from `mint`.
   *
   * `expiresIn` on a reused token is the time it has left, not its lifetime.
   */
  async get<T extends MintedToken>(key: string, mint: () => Promise<T>): Promise<T> {
    const cached = this.entries.get(key);
    if (cached && this.isReusable(cached)) {
      const token = (await cached.minted) as T;
      if (cached.expiresAt === undefined) return token;
      return { ...token, expiresIn: Math.floor((cached.expiresAt - this.now()) / 1000) };
    }

    this.dropUnusable();
    const requestedAt = this.now();
    const minted = mint();
    const entry: Entry = { minted, requestedAt };
    this.entries.set(key, entry);
    try {
      const token = await minted;
      // Counted from the request, not the reply: the hub's clock started first.
      entry.expiresAt = entry.requestedAt + (token.expiresIn ?? 0) * 1000;
      return token;
    } catch (error) {
      // A failed mint is not remembered; clear() may already have dropped it.
      if (this.entries.get(key) === entry) this.entries.delete(key);
      throw error;
    }
  }

  /** Drop every token. Call when the signed-in identity changes. */
  clear(): void {
    this.entries.clear();
  }

  private isReusable(entry: Entry): boolean {
    if (entry.expiresAt === undefined) return true;
    const now = this.now();
    // A clock set backwards would make an old token look fresh.
    if (now < entry.requestedAt) return false;
    return entry.expiresAt - now >= MIN_REMAINING_SECONDS * 1000;
  }

  private dropUnusable(): void {
    for (const [key, entry] of this.entries) {
      if (!this.isReusable(entry)) this.entries.delete(key);
    }
  }
}
