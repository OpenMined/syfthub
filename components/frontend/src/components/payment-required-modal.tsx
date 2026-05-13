/**
 * PaymentRequiredModal — Batched on-chain payment approval.
 *
 * Surfaces one or more `payment_required` challenges (emitted by the
 * aggregator's transaction policy) and lets the user approve them as a
 * single batch with their Tempo wallet passphrase.
 *
 * Each approved challenge is signed locally (ERC-20 transfer over the
 * Tempo RPC) and the resulting `Payment <base64...>` credential is POSTed
 * back to the aggregator's `/chat/{session_id}/payment` endpoint. Per-card
 * progress and per-card retry on failure.
 *
 * On all-success, calls `onApproved`. On user cancel, calls `onCanceled`
 * (the parent typically aborts the chat upstream).
 *
 * SECURITY: requires the user to supply the passphrase to decrypt their
 * locally-stored Tempo wallet (see `tempo-wallet-context.tsx`). The
 * decrypted key never leaves memory and is auto-locked after 5 minutes
 * by the wallet context.
 */
import { useCallback, useMemo, useRef, useState } from 'react';

import type { PaymentChallenge } from '@/hooks/use-chat-workflow';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal';
import { parseChallenge, useWalletForPayments } from '@/lib/payment-stubs';
import { syftClient } from '@/lib/sdk-client';

// =============================================================================
// Types
// =============================================================================

export interface PaymentRequiredModalProps {
  /** Challenges to present as a single batched approval. */
  challenges: PaymentChallenge[];
  /** Aggregator base URL — challenges POST to `${aggregatorURL}/chat/{session}/payment`. */
  aggregatorURL: string;
  /** Tempo RPC URL for signing/broadcasting the on-chain ERC-20 transfer. */
  rpcURL: string;
  /** EVM chain ID (Tempo testnet or mainnet). */
  chainID: number;
  /** ERC-20 decimals (default 6 for PathUSD). */
  decimals?: number;
  /** Called when all challenges in the batch were approved + verified. */
  onApproved: (results: Array<{ challengeID: string; txHash: string }>) => void;
  /** Called when the user cancels (parent aborts the chat). */
  onCanceled: () => void;
}

type ProgressStatus = 'pending' | 'signing' | 'submitted' | 'failed';

// =============================================================================
// LocalStorage payment history
// =============================================================================

const PAYMENT_HISTORY_KEY = 'syft_payment_history_v1';

interface PaymentHistoryEntry {
  timestamp: string;
  endpoint_slug: string;
  amount: string;
  currency: string;
  tx_hash: string;
  status: 'verified';
}

function appendPaymentHistory(entry: PaymentHistoryEntry): void {
  try {
    const raw = globalThis.localStorage.getItem(PAYMENT_HISTORY_KEY);
    const list = raw ? (JSON.parse(raw) as PaymentHistoryEntry[]) : [];
    list.push(entry);
    globalThis.localStorage.setItem(PAYMENT_HISTORY_KEY, JSON.stringify(list));
  } catch {
    // Best-effort; never block the flow on history persistence.
  }
}

// =============================================================================
// Display helpers
// =============================================================================

function truncateAddress(addr: string): string {
  if (addr.length <= 10) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

function displayName(c: PaymentChallenge): string {
  return c.ownerName ? `${c.ownerName}/${c.endpointSlug}` : c.endpointSlug;
}

/** Sums `amount` strings per currency. Returns `[currency, sumString][]`. */
function totalsByCurrency(
  challenges: PaymentChallenge[]
): Array<{ currency: string; total: string }> {
  // Decimal sum without floating-point: split on '.', track integer + 8-digit
  // fractional accumulator. Sufficient for the small number of challenges we
  // batch and keeps the math reproducible.
  const FRAC_DIGITS = 8;
  const groups = new Map<string, bigint>();
  for (const c of challenges) {
    const trimmed = c.amount.trim();
    if (!/^\d{1,32}(\.\d{1,32})?$/.test(trimmed)) continue;
    const [intPartRaw = '0', fracPartRaw = ''] = trimmed.split('.');
    const padded = (fracPartRaw + '0'.repeat(FRAC_DIGITS)).slice(0, FRAC_DIGITS);
    const scaled = BigInt(intPartRaw + padded);
    groups.set(c.currency, (groups.get(c.currency) ?? 0n) + scaled);
  }
  return [...groups].map(([currency, total]) => {
    const s = total.toString().padStart(FRAC_DIGITS + 1, '0');
    const intPart = s.slice(0, -FRAC_DIGITS);
    // Strip trailing zeros without a backtracking-prone regex.
    let fracPart = s.slice(-FRAC_DIGITS);
    let end = fracPart.length;
    while (end > 0 && fracPart[end - 1] === '0') end -= 1;
    fracPart = fracPart.slice(0, end);
    return { currency, total: fracPart ? `${intPart}.${fracPart}` : intPart };
  });
}

// =============================================================================
// Component
// =============================================================================

export function PaymentRequiredModal({
  challenges,
  aggregatorURL,
  rpcURL,
  chainID,
  decimals,
  onApproved,
  onCanceled
}: Readonly<PaymentRequiredModalProps>) {
  const wallet = useWalletForPayments();
  const [passphrase, setPassphrase] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Map<string, string>>(() => new Map());
  const [progress, setProgress] = useState<Map<string, ProgressStatus>>(() => {
    const m = new Map<string, ProgressStatus>();
    for (const c of challenges) m.set(c.challengeId, 'pending');
    return m;
  });
  const successesReference = useRef<Map<string, string>>(new Map()); // challengeID → txHash

  const totals = useMemo(() => totalsByCurrency(challenges), [challenges]);
  const failedChallenges = useMemo(
    () => challenges.filter((c) => progress.get(c.challengeId) === 'failed'),
    [challenges, progress]
  );
  const allDone = useMemo(
    () => challenges.every((c) => progress.get(c.challengeId) === 'submitted'),
    [challenges, progress]
  );

  // ---------------------------------------------------------------------------
  // Per-challenge processing
  // ---------------------------------------------------------------------------

  const updateProgress = useCallback((id: string, status: ProgressStatus): void => {
    setProgress((previous) => {
      const next = new Map(previous);
      next.set(id, status);
      return next;
    });
  }, []);

  const updateError = useCallback((id: string, message: string): void => {
    setErrors((previous) => {
      const next = new Map(previous);
      next.set(id, message);
      return next;
    });
  }, []);

  const clearError = useCallback((id: string): void => {
    setErrors((previous) => {
      if (!previous.has(id)) return previous;
      const next = new Map(previous);
      next.delete(id);
      return next;
    });
  }, []);

  const processOne = useCallback(
    async (challenge: PaymentChallenge): Promise<void> => {
      // Skip already-submitted challenges (retry path).
      if (successesReference.current.has(challenge.challengeId)) return;

      clearError(challenge.challengeId);
      updateProgress(challenge.challengeId, 'signing');

      let credential: string;
      let txHash: `0x${string}`;
      try {
        const parsed = parseChallenge(challenge.challenge);
        const signed = await wallet.signCredential(parsed, {
          rpcUrl: rpcURL,
          chainId: chainID,
          decimals
        });
        credential = signed.credential;
        txHash = signed.txHash;
      } catch (error) {
        updateError(
          challenge.challengeId,
          `Sign failed: ${error instanceof Error ? error.message : String(error)}`
        );
        updateProgress(challenge.challengeId, 'failed');
        return;
      }

      try {
        const tokens = syftClient.getTokens();
        const accessToken = tokens?.accessToken ?? '';
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

        const response = await fetch(
          `${aggregatorURL.replace(/\/$/, '')}/chat/${encodeURIComponent(
            challenge.chatSessionId
          )}/payment`,
          {
            method: 'POST',
            headers,
            body: JSON.stringify({
              challenge_id: challenge.challengeId,
              credential
            })
          }
        );
        if (!response.ok) {
          const text = await response.text().catch(() => '');
          throw new Error(`HTTP ${String(response.status)}${text ? `: ${text}` : ''}`);
        }
      } catch (error) {
        updateError(
          challenge.challengeId,
          `Submit failed: ${error instanceof Error ? error.message : String(error)}`
        );
        updateProgress(challenge.challengeId, 'failed');
        return;
      }

      successesReference.current.set(challenge.challengeId, txHash);
      appendPaymentHistory({
        timestamp: new Date().toISOString(),
        endpoint_slug: challenge.endpointSlug,
        amount: challenge.amount,
        currency: challenge.currency,
        tx_hash: txHash,
        status: 'verified'
      });
      updateProgress(challenge.challengeId, 'submitted');
    },
    [wallet, rpcURL, chainID, decimals, aggregatorURL, clearError, updateError, updateProgress]
  );

  // ---------------------------------------------------------------------------
  // Approve all (or retry only failed)
  // ---------------------------------------------------------------------------

  const runBatch = useCallback(
    async (only: PaymentChallenge[]): Promise<void> => {
      if (only.length === 0) return;
      setIsProcessing(true);
      setGlobalError(null);

      try {
        if (!wallet.isUnlocked) {
          try {
            await wallet.unlockWallet(passphrase);
          } catch (error) {
            setGlobalError(
              `Unlock failed: ${error instanceof Error ? error.message : String(error)}`
            );
            setIsProcessing(false);
            return;
          }
        }

        await Promise.allSettled(only.map((c) => processOne(c)));

        // If after this pass everything succeeded, fire onApproved.
        const allSucceeded = challenges.every((c) => successesReference.current.has(c.challengeId));
        if (allSucceeded) {
          const results = challenges.map((c) => ({
            challengeID: c.challengeId,
            txHash: successesReference.current.get(c.challengeId) ?? ''
          }));
          onApproved(results);
        }
      } finally {
        setIsProcessing(false);
      }
    },
    [wallet, passphrase, processOne, challenges, onApproved]
  );

  const handleApproveAll = useCallback((): void => {
    void runBatch(challenges);
  }, [runBatch, challenges]);

  const handleRetryFailed = useCallback((): void => {
    void runBatch(failedChallenges);
  }, [runBatch, failedChallenges]);

  const handleCancel = useCallback((): void => {
    setPassphrase('');
    onCanceled();
  }, [onCanceled]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const noWallet = !wallet.hasWallet;
  const totalLabel =
    totals.length === 1
      ? `${totals[0]?.total ?? '0'} (${truncateAddress(totals[0]?.currency ?? '')})`
      : totals.map((t) => `${t.total} ${truncateAddress(t.currency)}`).join(' + ');
  const subtitle = `This chat costs ${totalLabel} across ${String(challenges.length)} endpoint${challenges.length === 1 ? '' : 's'}.`;

  return (
    <Modal
      isOpen
      onClose={handleCancel}
      title='Payment required'
      size='lg'
      closeOnOverlayClick={false}
      showCloseButton={!isProcessing}
    >
      <div className='space-y-4'>
        <p className='font-inter text-muted-foreground text-sm'>{subtitle}</p>

        {/* Per-challenge cards */}
        <ul className='space-y-2' aria-label='Payment challenges'>
          {challenges.map((c) => {
            const status = progress.get(c.challengeId) ?? 'pending';
            const errMessage = errors.get(c.challengeId);
            return (
              <li
                key={c.challengeId}
                className='border-border bg-card flex flex-col gap-1 rounded-lg border p-3'
                data-testid={`challenge-${c.challengeId}`}
              >
                <div className='flex items-center justify-between gap-2'>
                  <div className='font-inter text-foreground min-w-0 truncate text-sm font-medium'>
                    {displayName(c)}
                  </div>
                  <StatusIcon status={status} />
                </div>
                <div className='font-inter text-muted-foreground flex flex-wrap gap-x-3 text-xs'>
                  <span>
                    Amount: <span className='text-foreground'>{c.amount}</span>
                  </span>
                  <span>
                    Recipient:{' '}
                    <span className='text-foreground'>{truncateAddress(c.recipient)}</span>
                  </span>
                </div>
                <details className='font-inter text-muted-foreground text-xs'>
                  <summary className='hover:text-foreground cursor-pointer'>View challenge</summary>
                  <pre className='bg-muted mt-1 max-h-32 overflow-auto rounded p-2 text-[10px] break-all whitespace-pre-wrap'>
                    {c.challenge}
                  </pre>
                </details>
                {errMessage && (
                  <div className='font-inter text-xs text-red-600 dark:text-red-400'>
                    {errMessage}
                  </div>
                )}
              </li>
            );
          })}
        </ul>

        {/* Wallet status */}
        <div className='font-inter text-muted-foreground text-xs' data-testid='wallet-status'>
          {noWallet ? (
            <span>
              Create a wallet first.{' '}
              <a className='text-primary underline underline-offset-2' href='/profile'>
                Open settings
              </a>
            </span>
          ) : (
            <span>Wallet: {wallet.address ? truncateAddress(wallet.address) : 'unknown'}</span>
          )}
        </div>

        {/* Passphrase */}
        {!noWallet && !wallet.isUnlocked && (
          <div className='space-y-1'>
            <label
              htmlFor='payment-passphrase'
              className='font-inter text-foreground text-xs font-medium'
            >
              Wallet passphrase
            </label>
            <Input
              id='payment-passphrase'
              type='password'
              autoComplete='current-password'
              value={passphrase}
              onChange={(event) => {
                setPassphrase(event.target.value);
              }}
              disabled={isProcessing}
              placeholder='Enter passphrase to unlock'
            />
          </div>
        )}

        {globalError && (
          <div className='font-inter rounded-md border border-red-200/60 bg-red-50/60 p-3 text-xs text-red-700 dark:border-red-800/40 dark:bg-red-950/40 dark:text-red-300'>
            {globalError}
          </div>
        )}

        {/* Actions */}
        <div className='flex flex-wrap items-center justify-end gap-2 pt-2'>
          <Button variant='outline' onClick={handleCancel} disabled={isProcessing}>
            Cancel
          </Button>
          {failedChallenges.length > 0 && !allDone && !isProcessing && (
            <Button variant='outline' onClick={handleRetryFailed}>
              Retry failed
            </Button>
          )}
          <Button
            onClick={handleApproveAll}
            disabled={
              isProcessing || noWallet || (failedChallenges.length > 0 && !isProcessing) || allDone
            }
          >
            {isProcessing ? 'Processing…' : 'Approve all'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

function StatusIcon({ status }: Readonly<{ status: ProgressStatus }>) {
  switch (status) {
    case 'pending': {
      return (
        <span
          aria-label='pending'
          className='bg-muted-foreground/30 inline-block h-2.5 w-2.5 rounded-full'
        />
      );
    }
    case 'signing': {
      return (
        <span
          aria-label='signing'
          className='border-primary inline-block h-3 w-3 animate-spin rounded-full border-2 border-t-transparent'
        />
      );
    }
    case 'submitted': {
      return (
        <span
          aria-label='submitted'
          className='inline-flex h-4 w-4 items-center justify-center rounded-full bg-green-500/20 text-xs font-semibold text-green-700 dark:text-green-400'
        >
          ✓
        </span>
      );
    }
    case 'failed': {
      return (
        <span
          aria-label='failed'
          className='inline-flex h-4 w-4 items-center justify-center rounded-full bg-red-500/20 text-xs font-semibold text-red-700 dark:text-red-400'
        >
          ✕
        </span>
      );
    }
  }
}
