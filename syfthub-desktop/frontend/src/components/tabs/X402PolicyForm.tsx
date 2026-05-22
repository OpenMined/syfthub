// Dedicated configuration form for the X402PayPerRequestPolicy.
//
// Producers gate their endpoint on an on-chain payment; this form
// collects the knobs the Python policy supports (price, currency,
// network, TTL, per-payer cap, allow-list). The pay_to field is NOT
// editable here — it is sourced from the host's local wallet
// (WalletShow) so the UI cannot misroute payments to an attacker-
// controlled address. When no wallet exists yet, the form shows a
// CTA that runs WalletInit and refreshes.
//
// Submission shape mirrors NewPolicyRequest in endpoint_operations.go:
// the X402 field carries the form values, which generatePolicyYAML
// folds into the template alongside the wallet-derived pay_to.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Wallet, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { CreatePolicyFile } from '../../../wailsjs/go/main/App';
import { main } from '../../../wailsjs/go/models';

// pathUSD on Tempo testnet — matches wallet_operations.go constants.
const PATH_USD_ADDRESS = '0x20c0000000000000000000000000000000000000';
const PATH_USD_DECIMALS = 6;
const TEMPO_TESTNET_CHAIN_ID = 42431;
const DEFAULT_TTL_SECONDS = 300;
const DEFAULT_MAX_PENDING = 16;
const MIN_TTL_SECONDS = 60;
const MAX_TTL_SECONDS = 3600;
const MIN_MAX_PENDING = 1;
const MAX_MAX_PENDING = 256;

// Wails bindings for wallet methods are not regenerated as part of the
// frontend `tsc && vite build` pipeline (they refresh on `wails build`),
// so we access them through the runtime-injected `window.go.main.App`
// object. The shapes here mirror wallet_operations.go.
interface WalletInfo {
  address: string;
  chain_id: number;
  rpc_url: string;
  network: string;
  key_exists: boolean;
}

interface WailsApp {
  WalletShow: () => Promise<WalletInfo>;
  WalletInit: () => Promise<WalletInfo>;
}

function wailsApp(): WailsApp {
  // window.go.main.App is populated by Wails at runtime; the runtime
  // bindings are not part of the static .d.ts. Cast via unknown to keep
  // the rest of the file strictly typed.
  return (window as unknown as { go: { main: { App: WailsApp } } }).go.main.App;
}

function isSlug(value: string): boolean {
  return /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(value);
}

function isPositiveDecimal(value: string, maxDecimals: number): boolean {
  if (!/^\d+(\.\d+)?$/.test(value)) return false;
  const [, frac = ''] = value.split('.');
  if (frac.length > maxDecimals) return false;
  return Number(value) > 0;
}

export interface X402PolicyFormProps {
  endpointSlug: string;
  onCreated: () => void;
  onCancel: () => void;
}

interface CurrencyChoice {
  id: 'pathusd' | 'custom';
  label: string;
}

const CURRENCY_CHOICES: CurrencyChoice[] = [
  { id: 'pathusd', label: 'pathUSD (default)' },
  { id: 'custom', label: 'Custom ERC-20…' },
];

const CHAIN_CHOICES = [
  { id: TEMPO_TESTNET_CHAIN_ID, label: 'Tempo testnet (42431)' },
];

export function X402PolicyForm({ endpointSlug, onCreated, onCancel }: X402PolicyFormProps) {
  const [name, setName] = useState('');
  const [price, setPrice] = useState('0.01');
  const [currencyChoice, setCurrencyChoice] = useState<CurrencyChoice['id']>('pathusd');
  const [customCurrency, setCustomCurrency] = useState('');
  const [chainId, setChainId] = useState<number>(TEMPO_TESTNET_CHAIN_ID);
  const [realm, setRealm] = useState('');
  const [realmTouched, setRealmTouched] = useState(false);
  const [ttlSeconds, setTtlSeconds] = useState<number>(DEFAULT_TTL_SECONDS);
  const [maxPending, setMaxPending] = useState<number>(DEFAULT_MAX_PENDING);
  const [allowListInput, setAllowListInput] = useState('');
  const [allowList, setAllowList] = useState<string[]>([]);

  const [wallet, setWallet] = useState<WalletInfo | null>(null);
  const [walletLoading, setWalletLoading] = useState(true);
  const [walletError, setWalletError] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const refreshWallet = useCallback(async () => {
    setWalletLoading(true);
    setWalletError(null);
    try {
      const info = await wailsApp().WalletShow();
      setWallet(info);
    } catch (err) {
      setWalletError(`Failed to load wallet: ${err}`);
    } finally {
      setWalletLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshWallet();
  }, [refreshWallet]);

  // Keep the default realm in lockstep with (slug, name) until the user
  // edits it themselves — once they do, leave it alone.
  useEffect(() => {
    if (realmTouched) return;
    const derived = name.trim()
      ? `syfthub:endpoint:${endpointSlug}:${name.trim()}`
      : '';
    setRealm(derived);
  }, [endpointSlug, name, realmTouched]);

  const initWallet = async () => {
    setWalletLoading(true);
    setWalletError(null);
    try {
      const info = await wailsApp().WalletInit();
      setWallet(info);
    } catch (err) {
      setWalletError(`Failed to initialise wallet: ${err}`);
    } finally {
      setWalletLoading(false);
    }
  };

  const addAllowListEntry = () => {
    const trimmed = allowListInput.trim();
    if (!trimmed) return;
    if (allowList.includes(trimmed)) {
      setAllowListInput('');
      return;
    }
    setAllowList([...allowList, trimmed]);
    setAllowListInput('');
  };

  const removeAllowListEntry = (entry: string) => {
    setAllowList(allowList.filter((e) => e !== entry));
  };

  const effectiveCurrency = useMemo(() => {
    if (currencyChoice === 'pathusd') return PATH_USD_ADDRESS;
    return customCurrency.trim();
  }, [currencyChoice, customCurrency]);

  const effectiveDecimals = currencyChoice === 'pathusd' ? PATH_USD_DECIMALS : PATH_USD_DECIMALS;

  // Validation aggregated into one place so the Save button reflects it.
  const nameValid = isSlug(name.trim());
  const priceValid = isPositiveDecimal(price.trim(), effectiveDecimals);
  const currencyValid =
    currencyChoice === 'pathusd'
      ? true
      : /^0x[a-fA-F0-9]{40}$/.test(effectiveCurrency);
  const ttlValid =
    Number.isInteger(ttlSeconds) &&
    ttlSeconds >= MIN_TTL_SECONDS &&
    ttlSeconds <= MAX_TTL_SECONDS;
  const maxPendingValid =
    Number.isInteger(maxPending) &&
    maxPending >= MIN_MAX_PENDING &&
    maxPending <= MAX_MAX_PENDING;
  const walletReady = wallet?.key_exists === true;
  const canSubmit =
    nameValid && priceValid && currencyValid && ttlValid && maxPendingValid && walletReady && !saving;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSaving(true);
    setSubmitError(null);
    try {
      // The generated NewPolicyRequest class carries a convertValues
      // helper method (added when the nested X402PolicyConfig class
      // appeared). The Wails runtime serializes plain JSON over the
      // wire, so the helper is irrelevant at runtime — we cast through
      // unknown rather than construct the class for a wire payload.
      const payload = {
        name: name.trim(),
        type: 'X402PayPerRequestPolicy',
        childPolicies: [],
        denyReason: '',
        x402: {
          price: price.trim(),
          currency: effectiveCurrency,
          decimals: effectiveDecimals,
          chainId,
          realm: realm.trim(),
          hmacSecretKid: 'default',
          challengeTtlSeconds: ttlSeconds,
          maxPendingSettlementsPerPayer: maxPending,
          allowListedPayers: allowList,
        },
      } as unknown as main.NewPolicyRequest;
      await CreatePolicyFile(endpointSlug, payload);
      onCreated();
    } catch (err) {
      setSubmitError(`${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-medium text-foreground">New x402 Pay-Per-Request Policy</h3>
        <p className="text-xs text-muted-foreground mt-1">
          Charge payers on-chain (Tempo pathUSD) per request; settle on handler success.
        </p>
      </div>

      {/* Wallet status / pay_to (read-only) */}
      <div className="rounded-md border border-border bg-background/40 p-3 space-y-2">
        <div className="flex items-center gap-2">
          <Wallet className="w-4 h-4 text-muted-foreground" />
          <span className="text-xs text-muted-foreground">
            Pay to
            <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] bg-primary/15 text-primary">
              your wallet
            </span>
          </span>
        </div>
        {walletLoading ? (
          <p className="text-xs text-muted-foreground">Loading wallet…</p>
        ) : walletError ? (
          <p className="text-xs text-destructive">{walletError}</p>
        ) : walletReady ? (
          <p className="font-mono text-xs text-foreground break-all">{wallet!.address}</p>
        ) : (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              No wallet on this device yet. Generate one so payments can be received.
            </p>
            <Button size="sm" onClick={initWallet} disabled={walletLoading} className="h-7 text-xs">
              Initialise wallet
            </Button>
          </div>
        )}
      </div>

      {/* Name */}
      <div className="space-y-1.5">
        <label className="text-xs text-muted-foreground">Policy name</label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g., pay-per-call"
          className="h-9"
          autoFocus
        />
        {name && !nameValid && (
          <p className="text-xs text-destructive">
            Use letters, digits, hyphens or underscores (max 64 chars, must start with alnum).
          </p>
        )}
      </div>

      {/* Price */}
      <div className="space-y-1.5">
        <label className="text-xs text-muted-foreground">
          Price per request ({effectiveDecimals} decimals max)
        </label>
        <Input
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder="0.01"
          className="h-9 font-mono"
          inputMode="decimal"
        />
        {price && !priceValid && (
          <p className="text-xs text-destructive">
            Must be a positive decimal with at most {effectiveDecimals} fractional digits.
          </p>
        )}
      </div>

      {/* Currency */}
      <div className="space-y-1.5">
        <label className="text-xs text-muted-foreground">Currency</label>
        <Select value={currencyChoice} onValueChange={(v) => setCurrencyChoice(v as CurrencyChoice['id'])}>
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {CURRENCY_CHOICES.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        {currencyChoice === 'custom' && (
          <Input
            value={customCurrency}
            onChange={(e) => setCustomCurrency(e.target.value)}
            placeholder="0x… ERC-20 contract address"
            className="h-9 font-mono"
          />
        )}
        {currencyChoice === 'custom' && customCurrency && !currencyValid && (
          <p className="text-xs text-destructive">Enter a valid 0x-prefixed 40-hex address.</p>
        )}
      </div>

      {/* Chain */}
      <div className="space-y-1.5">
        <label className="text-xs text-muted-foreground">Network</label>
        <Select
          value={String(chainId)}
          onValueChange={(v) => setChainId(Number(v))}
        >
          <SelectTrigger className="h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {CHAIN_CHOICES.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
      </div>

      {/* Realm */}
      <div className="space-y-1.5">
        <label className="text-xs text-muted-foreground">Realm</label>
        <Input
          value={realm}
          onChange={(e) => {
            setRealm(e.target.value);
            setRealmTouched(true);
          }}
          placeholder="syfthub:endpoint:slug:policy"
          className="h-9 font-mono text-xs"
        />
        <p className="text-xs text-muted-foreground/70">
          Identifies the challenge namespace. Defaults to{' '}
          <code className="font-mono">syfthub:endpoint:{endpointSlug}:&lt;name&gt;</code>.
        </p>
      </div>

      {/* TTL + max pending side by side */}
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">
            Challenge TTL (seconds, {MIN_TTL_SECONDS}–{MAX_TTL_SECONDS})
          </label>
          <Input
            value={String(ttlSeconds)}
            onChange={(e) => setTtlSeconds(Number(e.target.value))}
            type="number"
            min={MIN_TTL_SECONDS}
            max={MAX_TTL_SECONDS}
            className="h-9 font-mono"
          />
          {!ttlValid && (
            <p className="text-xs text-destructive">
              Must be between {MIN_TTL_SECONDS} and {MAX_TTL_SECONDS}.
            </p>
          )}
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">
            Max pending settlements per payer ({MIN_MAX_PENDING}–{MAX_MAX_PENDING})
          </label>
          <Input
            value={String(maxPending)}
            onChange={(e) => setMaxPending(Number(e.target.value))}
            type="number"
            min={MIN_MAX_PENDING}
            max={MAX_MAX_PENDING}
            className="h-9 font-mono"
          />
          {!maxPendingValid && (
            <p className="text-xs text-destructive">
              Must be between {MIN_MAX_PENDING} and {MAX_MAX_PENDING}.
            </p>
          )}
        </div>
      </div>

      {/* Allow-list */}
      <div className="space-y-1.5">
        <label className="text-xs text-muted-foreground">
          Allow-listed payers (optional — bypass payment)
        </label>
        <div className="flex gap-2">
          <Input
            value={allowListInput}
            onChange={(e) => setAllowListInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                addAllowListEntry();
              }
            }}
            placeholder="user@example.com"
            className="h-9 font-mono text-xs"
          />
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-9"
            onClick={addAllowListEntry}
            disabled={!allowListInput.trim()}
          >
            Add
          </Button>
        </div>
        {allowList.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {allowList.map((entry) => (
              <span
                key={entry}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-secondary/50 text-xs"
              >
                <span className="font-mono">{entry}</span>
                <button
                  type="button"
                  onClick={() => removeAllowListEntry(entry)}
                  className="text-muted-foreground hover:text-destructive"
                  aria-label={`Remove ${entry}`}
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {submitError && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
          {submitError}
        </div>
      )}

      <div className="flex justify-end gap-2 pt-2 border-t border-border/50">
        <Button variant="outline" size="sm" onClick={onCancel} className="h-8">
          Cancel
        </Button>
        <Button size="sm" onClick={handleSubmit} disabled={!canSubmit} className="h-8">
          {saving ? 'Creating…' : 'Create Policy'}
        </Button>
      </div>
    </div>
  );
}
