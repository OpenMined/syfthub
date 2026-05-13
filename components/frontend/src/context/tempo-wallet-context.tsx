/**
 * Tempo Wallet Context — Browser-Local Payment Wallet
 *
 * SECURITY: This wallet stores a passphrase-encrypted private key in
 * localStorage. The decrypted key lives in memory while the wallet is
 * unlocked (max 5 min auto-lock). This is vulnerable to XSS — any malicious
 * script loaded in the SyftHub frontend could exfiltrate the unlocked key
 * or replace the encrypted blob.
 *
 * This v1 implementation is intended for testnet use only. v2 will move
 * the key into the OS keyring via a Wails bridge for the desktop app.
 * Browser users should fund the wallet only with the minimum amount
 * needed for current usage.
 *
 * NOTE: distinct from `wallet-context.tsx`, which manages the SyftHub
 * backend (Xendit credit) wallet. This context is only for on-chain
 * Tempo (MPP) payments emitted by the aggregator transaction policy.
 */

import React, { createContext, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { ParsedChallenge, SignedCredential } from '@/lib/tempo-wallet-mpp';

import {
  decryptPrivateKey,
  encryptPrivateKey,
  generatePrivateKey,
  privateKeyToAddress
} from '@/lib/tempo-wallet-crypto';
import { readErc20Balance, signCredentialViaTempo } from '@/lib/tempo-wallet-mpp';

// =============================================================================
// Storage shape
// =============================================================================

const STORAGE_KEY = 'syft_wallet_v1';
/** Auto-lock the in-memory key after this many ms of inactivity. */
const AUTO_LOCK_MS = 5 * 60 * 1000;

interface StoredWallet {
  version: 1;
  address: `0x${string}`;
  ciphertext: string; // base64(salt|nonce|ciphertext+tag)
}

function readStored(): StoredWallet | null {
  try {
    const raw = globalThis.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredWallet>;
    if (
      parsed.version !== 1 ||
      typeof parsed.address !== 'string' ||
      typeof parsed.ciphertext !== 'string'
    ) {
      return null;
    }
    return parsed as StoredWallet;
  } catch {
    return null;
  }
}

function writeStored(value: StoredWallet): void {
  globalThis.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

function clearStored(): void {
  globalThis.localStorage.removeItem(STORAGE_KEY);
}

// =============================================================================
// Context
// =============================================================================

export interface TempoWalletContextValue {
  /** Wallet EVM address, or null if no wallet has been created. */
  address: `0x${string}` | null;
  /** True iff a wallet is persisted in localStorage. */
  hasWallet: boolean;
  /** True iff the private key is currently decrypted in memory. */
  isUnlocked: boolean;
  /**
   * Generates a new wallet, encrypts it with the passphrase, persists it,
   * and immediately leaves it unlocked. Throws if a wallet already exists.
   */
  createWallet: (passphrase: string) => Promise<{ address: `0x${string}` }>;
  /**
   * Decrypts the stored wallet and caches the private key in memory for
   * up to AUTO_LOCK_MS. Throws on wrong passphrase.
   */
  unlockWallet: (passphrase: string) => Promise<void>;
  /** Wipes the in-memory private key. Does NOT delete the stored ciphertext. */
  lockWallet: () => void;
  /** Removes the wallet from localStorage AND wipes any in-memory key. */
  resetWallet: () => void;
  /**
   * Signs an MPP credential by sending an on-chain Tempo ERC-20 transfer.
   * Requires the wallet to be unlocked; throws otherwise. Resets the
   * auto-lock timer on each call.
   */
  signCredential: (
    challenge: ParsedChallenge,
    options: { rpcUrl: string; chainId: number; decimals?: number }
  ) => Promise<SignedCredential>;
  /** Reads the ERC-20 balance of the wallet for the given currency. */
  getBalance: (options: {
    rpcUrl: string;
    chainId: number;
    currency: `0x${string}`;
  }) => Promise<bigint>;
}

export const TempoWalletContext = createContext<TempoWalletContextValue | undefined>(undefined);

// =============================================================================
// Provider
// =============================================================================

interface TempoWalletProviderProps {
  children: React.ReactNode;
}

export function TempoWalletProvider({ children }: Readonly<TempoWalletProviderProps>) {
  const [address, setAddress] = useState<`0x${string}` | null>(null);
  const [isUnlocked, setIsUnlocked] = useState(false);

  // The decrypted private key lives ONLY in this ref — never in state, never
  // in localStorage post-unlock — to keep it out of React DevTools snapshots
  // and any stray re-render observation surface.
  const privateKeyReference = useRef<Uint8Array | null>(null);
  const lockTimerReference = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---------------------------------------------------------------------------
  // In-memory key lifecycle
  // ---------------------------------------------------------------------------

  const wipeKey = useCallback((): void => {
    if (privateKeyReference.current) {
      privateKeyReference.current.fill(0);
      privateKeyReference.current = null;
    }
    if (lockTimerReference.current) {
      clearTimeout(lockTimerReference.current);
      lockTimerReference.current = null;
    }
  }, []);

  const lockWallet = useCallback((): void => {
    wipeKey();
    setIsUnlocked(false);
  }, [wipeKey]);

  const armLockTimer = useCallback((): void => {
    if (lockTimerReference.current) clearTimeout(lockTimerReference.current);
    lockTimerReference.current = setTimeout(() => {
      lockWallet();
    }, AUTO_LOCK_MS);
  }, [lockWallet]);

  // Mount: hydrate address from storage. We do NOT decrypt here.
  useEffect(() => {
    const stored = readStored();
    if (stored) setAddress(stored.address);
    return () => {
      wipeKey();
    };
  }, [wipeKey]);

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const createWallet = useCallback(
    async (passphrase: string): Promise<{ address: `0x${string}` }> => {
      if (readStored()) {
        throw new Error('A wallet already exists. Reset it first to create a new one.');
      }
      const key = generatePrivateKey();
      const ciphertext = await encryptPrivateKey(key, passphrase);
      const addr = privateKeyToAddress(key);
      writeStored({ version: 1, address: addr, ciphertext });

      // Cache the freshly-generated key so the user can sign immediately.
      privateKeyReference.current = key;
      setAddress(addr);
      setIsUnlocked(true);
      armLockTimer();
      return { address: addr };
    },
    [armLockTimer]
  );

  const unlockWallet = useCallback(
    async (passphrase: string): Promise<void> => {
      const stored = readStored();
      if (!stored) throw new Error('No wallet to unlock');
      const key = await decryptPrivateKey(stored.ciphertext, passphrase);
      privateKeyReference.current = key;
      setIsUnlocked(true);
      armLockTimer();
    },
    [armLockTimer]
  );

  const resetWallet = useCallback((): void => {
    clearStored();
    wipeKey();
    setAddress(null);
    setIsUnlocked(false);
  }, [wipeKey]);

  const signCredential = useCallback(
    async (
      challenge: ParsedChallenge,
      options: { rpcUrl: string; chainId: number; decimals?: number }
    ): Promise<SignedCredential> => {
      const key = privateKeyReference.current;
      if (!key) throw new Error('Wallet is locked. Call unlockWallet first.');
      armLockTimer();
      return signCredentialViaTempo({
        challenge,
        privateKey: key,
        rpcUrl: options.rpcUrl,
        chainId: options.chainId,
        decimals: options.decimals
      });
    },
    [armLockTimer]
  );

  const getBalance = useCallback(
    async (options: {
      rpcUrl: string;
      chainId: number;
      currency: `0x${string}`;
    }): Promise<bigint> => {
      if (!address) throw new Error('No wallet address available');
      return readErc20Balance({
        address,
        rpcUrl: options.rpcUrl,
        chainId: options.chainId,
        currency: options.currency
      });
    },
    [address]
  );

  // ---------------------------------------------------------------------------
  // Context value
  // ---------------------------------------------------------------------------

  const value = useMemo<TempoWalletContextValue>(
    () => ({
      address,
      hasWallet: address !== null,
      isUnlocked,
      createWallet,
      unlockWallet,
      lockWallet,
      resetWallet,
      signCredential,
      getBalance
    }),
    [
      address,
      isUnlocked,
      createWallet,
      unlockWallet,
      lockWallet,
      resetWallet,
      signCredential,
      getBalance
    ]
  );

  return <TempoWalletContext.Provider value={value}>{children}</TempoWalletContext.Provider>;
}
