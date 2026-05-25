/**
 * PaymentRequiredModal — blocking prompt shown when the consumer hits an
 * x402-gated endpoint and `EvaluatePaymentDecision` returned "prompt".
 *
 * The modal carries a single payment_required event end-to-end:
 *  1. Display the endpoint, amount, currency, and recipient.
 *  2. Let the user either pay once, set a per-endpoint cap and pay, or cancel.
 *  3. On "Pay", sign the wire-format challenge via WalletPayChallenge and
 *     hand the resulting credential back to the caller (which retries the
 *     original request with payment_credential set).
 *  4. Surface wallet-not-initialised state with a CTA that runs WalletInit.
 *  5. Surface any sign/save error inline; the user can retry.
 */
import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp, Loader2, Wallet } from 'lucide-react';

import {
  SetPaymentCap,
  WalletInit,
  WalletPayChallenge,
  WalletShow,
} from '../../../wailsjs/go/main/App';
import { main } from '../../../wailsjs/go/models';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface PaymentRequiredModalProps {
  open: boolean;
  onClose: () => void;
  /** "owner/slug" pair the producer requested payment for. */
  endpointSlug: string;
  /** Display-friendly label for the endpoint (falls back to slug). */
  ownerLabel?: string;
  amount: string;
  currency: string;
  recipient: string;
  /** Wire-format payment_challenge from the producer (passed to WalletPayChallenge). */
  challengeWire: string;
  /**
   * Called after WalletPayChallenge succeeds with the serialized credential.
   * The chat workflow uses this credential to retry the original request.
   */
  onPaid: (credentialHex: string) => void | Promise<void>;
  /** Called when the user dismisses without paying. Distinct from onClose so
   *  callers can also distinguish "X clicked" from "Cancel clicked". */
  onCancel: () => void;
}

type SubmitMode = 'once' | 'with_cap';

const DEFAULT_SOFT_CAP = '0.10';
const DEFAULT_HARD_CAP = '1.00';

export function PaymentRequiredModal({
  open,
  onClose,
  endpointSlug,
  ownerLabel,
  amount,
  currency,
  recipient,
  challengeWire,
  onPaid,
  onCancel,
}: PaymentRequiredModalProps) {
  const [walletReady, setWalletReady] = useState<boolean | null>(null);
  const [walletAddress, setWalletAddress] = useState<string>('');
  const [walletChecking, setWalletChecking] = useState<boolean>(true);
  const [walletInitting, setWalletInitting] = useState<boolean>(false);

  const [submitting, setSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [showRecipient, setShowRecipient] = useState<boolean>(false);
  const [showCapEditor, setShowCapEditor] = useState<boolean>(false);
  // Seed the cap editor with values that, if confirmed verbatim, would
  // permit *this* payment to auto-pay next time. parseFloat can return NaN
  // for non-numeric input — guard so the seeded values stay valid.
  const parsedAmount = Number.parseFloat(amount);
  const parsedHardDefault = Number.parseFloat(DEFAULT_HARD_CAP);
  const seedSoftCap = amount && !Number.isNaN(parsedAmount) ? amount : DEFAULT_SOFT_CAP;
  const seedHardCap =
    amount && !Number.isNaN(parsedAmount) && parsedAmount > parsedHardDefault
      ? amount
      : DEFAULT_HARD_CAP;
  const [softCap, setSoftCap] = useState<string>(seedSoftCap);
  const [hardCap, setHardCap] = useState<string>(seedHardCap);

  // Reseed cap values every time the modal opens so a re-open for a
  // different endpoint/amount does not show stale values from the previous
  // invocation. useState only honours its initial value on first mount,
  // hence the explicit setSoftCap/setHardCap here.
  useEffect(() => {
    if (!open) return;
    setSoftCap(seedSoftCap);
    setHardCap(seedHardCap);
    // seedSoftCap/seedHardCap are derived from `amount` only — including
    // them in the dep list would not change behaviour because `amount`
    // already triggers re-renders, but eslint-react-hooks needs them.
  }, [open, seedSoftCap, seedHardCap]);

  // Check wallet state on open. WalletShow does NOT generate a key — the
  // user must explicitly opt in via WalletInit. If KeyExists is false we
  // render the init CTA instead of the pay button.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setWalletChecking(true);
    setErrorMsg(null);
    setShowCapEditor(false);
    WalletShow()
      .then((info) => {
        if (cancelled) return;
        setWalletReady(info.key_exists);
        setWalletAddress(info.address ?? '');
      })
      .catch((err) => {
        if (cancelled) return;
        setWalletReady(false);
        setErrorMsg(`Wallet check failed: ${String(err)}`);
      })
      .finally(() => {
        if (!cancelled) setWalletChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Reset transient state when the modal closes so the next open starts clean.
  useEffect(() => {
    if (!open) {
      setSubmitting(false);
      setErrorMsg(null);
      setShowRecipient(false);
      setShowCapEditor(false);
    }
  }, [open]);

  const handleInitWallet = useCallback(async () => {
    setWalletInitting(true);
    setErrorMsg(null);
    try {
      const info = await WalletInit();
      setWalletReady(info.key_exists);
      setWalletAddress(info.address ?? '');
    } catch (err) {
      setErrorMsg(`Wallet init failed: ${String(err)}`);
    } finally {
      setWalletInitting(false);
    }
  }, []);

  const performPay = useCallback(
    async (mode: SubmitMode) => {
      if (submitting) return;
      setSubmitting(true);
      setErrorMsg(null);
      try {
        // 1. Persist the cap first (if requested) so that even if the user
        //    closes the app mid-flight, the cap survives. We persist BEFORE
        //    paying so the cap reflects the user's intent regardless of
        //    whether the sign succeeds.
        if (mode === 'with_cap') {
          // Client-side guard so the user gets immediate feedback before
          // the Wails round-trip — the Go side also rejects soft > hard
          // (payment_caps.go SetPaymentCap), but surfacing it here keeps
          // the UX responsive when the user types an obviously inverted
          // pair.
          const softVal = Number(softCap.trim() || DEFAULT_SOFT_CAP);
          const hardVal = Number(hardCap.trim() || DEFAULT_HARD_CAP);
          if (Number.isFinite(softVal) && Number.isFinite(hardVal) && softVal > hardVal) {
            throw new Error('Soft cap must be <= hard cap.');
          }
          await SetPaymentCap(
            main.PaymentCap.createFrom({
              endpoint_slug: endpointSlug,
              soft_cap: softCap.trim() || DEFAULT_SOFT_CAP,
              hard_cap: hardCap.trim() || DEFAULT_HARD_CAP,
              currency,
              updated_at: 0,
            }),
          );
        }
        // 2. Sign the challenge — produces a serialized mppx credential.
        //    Pass the display amount + currency we showed the user so the
        //    ledger records the human-readable value, not the token's base
        //    units (otherwise an 18-decimal token like DAI gets recorded as
        //    10^12× the real amount; see wallet_operations.go).
        const credential = await WalletPayChallenge(challengeWire, amount, currency);
        // 3. Hand the credential to the caller so it can resubmit the
        //    original request. await so any caller error surfaces inline.
        await onPaid(credential);
        // 4. Close — caller is responsible for resuming the chat flow.
        onClose();
      } catch (err) {
        setErrorMsg(String(err));
      } finally {
        setSubmitting(false);
      }
    },
    [
      challengeWire,
      currency,
      endpointSlug,
      hardCap,
      onClose,
      onPaid,
      softCap,
      submitting,
    ],
  );

  const handleCancel = useCallback(() => {
    if (submitting) return;
    onCancel();
    onClose();
  }, [onCancel, onClose, submitting]);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) handleCancel();
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wallet className="h-5 w-5" />
            Payment required
          </DialogTitle>
          <DialogDescription>
            <span className="font-medium">{ownerLabel || endpointSlug}</span>{' '}
            requires{' '}
            <span className="font-mono">
              {amount} {shortenCurrency(currency)}
            </span>{' '}
            to process this request. The payment will be settled on the Tempo
            network.
          </DialogDescription>
        </DialogHeader>

        {/* Recipient — collapsed by default so the modal stays compact. */}
        <div className="rounded-md border border-border/60 bg-muted/30 p-3 text-xs">
          <button
            type="button"
            onClick={() => setShowRecipient((v) => !v)}
            className="flex w-full items-center justify-between text-muted-foreground hover:text-foreground"
            aria-expanded={showRecipient}
          >
            <span>Recipient address</span>
            {showRecipient ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
          </button>
          {showRecipient && (
            <div className="mt-2 break-all font-mono text-[11px] text-foreground">
              {recipient || <span className="italic text-muted-foreground">(unknown)</span>}
            </div>
          )}
        </div>

        {/* Per-endpoint cap editor — collapses by default. Opens via the
            "Always allow" button below. */}
        {showCapEditor && (
          <div className="space-y-3 rounded-md border border-border/60 bg-muted/30 p-3">
            <div className="text-xs text-muted-foreground">
              Cap future {shortenCurrency(currency)} payments to{' '}
              <span className="font-medium text-foreground">{ownerLabel || endpointSlug}</span>:
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label htmlFor="soft-cap" className="text-xs">
                  Soft cap (auto-pay)
                </Label>
                <Input
                  id="soft-cap"
                  value={softCap}
                  onChange={(e) => setSoftCap(e.target.value)}
                  inputMode="decimal"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="hard-cap" className="text-xs">
                  Hard cap (toast)
                </Label>
                <Input
                  id="hard-cap"
                  value={hardCap}
                  onChange={(e) => setHardCap(e.target.value)}
                  inputMode="decimal"
                />
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Requests ≤ soft cap auto-pay silently. Between soft and hard cap, a toast
              announces the payment. Above hard cap, this modal opens again.
            </p>
          </div>
        )}

        {errorMsg && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="break-words">{errorMsg}</span>
          </div>
        )}

        {/* Wallet-not-initialised CTA. The pay buttons stay hidden while the
            user hasn't generated a key yet — paying would fail server-side. */}
        {!walletChecking && walletReady === false && (
          <div className="rounded-md border border-border/60 bg-card p-3 text-sm">
            <p className="mb-2 text-foreground">
              No wallet is set up on this device yet. SyftHub Desktop will generate a Tempo wallet
              locally so you can sign this payment.
            </p>
            <Button
              onClick={handleInitWallet}
              disabled={walletInitting}
              className="w-full"
              size="sm"
            >
              {walletInitting ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" /> Initialising…
                </>
              ) : (
                <>
                  <Wallet className="h-3 w-3" /> Initialise wallet
                </>
              )}
            </Button>
          </div>
        )}

        {walletReady === true && walletAddress && (
          <div className="text-[11px] text-muted-foreground">
            Paying from <span className="font-mono">{shortAddr(walletAddress)}</span>
          </div>
        )}

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={handleCancel}
            disabled={submitting}
            className="sm:mr-auto"
          >
            Cancel
          </Button>
          {showCapEditor ? (
            <Button
              type="button"
              onClick={() => void performPay('with_cap')}
              disabled={submitting || walletChecking || walletReady !== true}
            >
              {submitting ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" /> Saving cap & paying…
                </>
              ) : (
                'Save cap & pay'
              )}
            </Button>
          ) : (
            <>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setShowCapEditor(true)}
                disabled={submitting || walletChecking || walletReady !== true}
              >
                Always allow ≤ {hardCap}
              </Button>
              <Button
                type="button"
                onClick={() => void performPay('once')}
                disabled={submitting || walletChecking || walletReady !== true}
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" /> Paying…
                  </>
                ) : (
                  'Pay once'
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Trim a long hex address to "0xabc…1234" for display. */
function shortAddr(addr: string): string {
  if (!addr || addr.length <= 12) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

/** Reduce a long currency identifier (e.g. a contract address) to a short
 *  display token. Returns the value unchanged when it's already short. */
function shortenCurrency(currency: string): string {
  if (!currency) return '';
  if (currency.length <= 12) return currency;
  return `${currency.slice(0, 6)}…${currency.slice(-4)}`;
}
