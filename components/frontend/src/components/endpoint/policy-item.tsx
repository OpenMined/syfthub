import React, { memo, useMemo, useState } from 'react';

import type { Policy } from '@/lib/types';
import type { PrepaidProvider } from './xendit-policy-content';

import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import Coins from 'lucide-react/dist/esm/icons/coins';
import CreditCard from 'lucide-react/dist/esm/icons/credit-card';
import Gauge from 'lucide-react/dist/esm/icons/gauge';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Info from 'lucide-react/dist/esm/icons/info';
import Key from 'lucide-react/dist/esm/icons/key';
import Lock from 'lucide-react/dist/esm/icons/lock';
import MapPin from 'lucide-react/dist/esm/icons/map-pin';
import Shield from 'lucide-react/dist/esm/icons/shield';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import Zap from 'lucide-react/dist/esm/icons/zap';

import { Badge } from '@/components/ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { parseXenditConfig, UNIT_LABEL } from '@/lib/xendit-client';

import { GenericPolicyContent } from './generic-policy-content';
import { MppPolicyContent } from './mpp-policy-content';
import { formatConfigKey } from './policy-format';
import { XenditPolicyContent } from './xendit-policy-content';

// Policy types that drive the prepaid-credits card. Both providers share the
// same config shape (bundles + currency + payment_url + credits_url +
// invoices_url + price + unit_type), so the card and BundlePicker are reused.
// Adding a future prepaid provider is one entry here plus a theme entry in
// POLICY_TYPE_CONFIG.
const PREPAID_BALANCE_TYPES = new Set<PrepaidProvider>(['xendit', 'stripe']);
function isPrepaidBalanceType(type: string): type is PrepaidProvider {
  return (PREPAID_BALANCE_TYPES as Set<string>).has(type);
}

// Pay-as-you-go (MPP) policy type. Shares the premium balance-card layout with
// the prepaid providers, but bills automatically per request out of the user's
// MPP wallet — so there is no bundle picker or "Buy credits" CTA. `mpp` is the
// single canonical type — exactly what syft-space publishes (the policy type is
// the wallet provider, `mpp`/`xendit`); legacy `mpp_accounting`/`accounting`/
// `transaction` spellings were collapsed into it. Keep in lockstep with the
// backend `_MPP_POLICY_TYPES`.
const MPP_BALANCE_TYPES = new Set<string>(['mpp']);
function isMppBalanceType(type: string): boolean {
  return MPP_BALANCE_TYPES.has(type);
}
// The MPP wallet provider is not encoded in policy.config — it is surfaced in
// the UI the same way the prepaid providers name themselves under the title.
const MPP_PROVIDER_LABEL = 'Tempo';

// Display name shown under a balance card's title, keyed by policy type (e.g.
// "via Xendit", "via Tempo"). Returns null for non-balance policy types.
const BALANCE_PROVIDER_LABELS: Record<string, string> = {
  xendit: 'Xendit',
  stripe: 'Stripe',
  mpp: MPP_PROVIDER_LABEL
};
function getBalanceProviderLabel(policyType: string): string | null {
  return BALANCE_PROVIDER_LABELS[policyType] ?? null;
}

// Shared styling/copy for the pay-as-you-go (MPP) policy types.
const MPP_POLICY_CONFIG = {
  icon: Coins,
  label: 'Pay as you go',
  color: 'text-emerald-600 dark:text-emerald-400',
  bgColor: 'bg-emerald-50 dark:bg-emerald-950/30',
  borderColor: 'border-emerald-200 dark:border-emerald-800',
  description: 'Pay-per-request billing deducted automatically from your MPP wallet.'
};

// Policy type configuration for styling and icons
const POLICY_TYPE_CONFIG: Record<
  string,
  {
    icon: React.ElementType;
    label: string;
    color: string;
    bgColor: string;
    borderColor: string;
    description: string;
  }
> = {
  // Pay-as-you-go pricing — the single canonical MPP type.
  mpp: MPP_POLICY_CONFIG,
  xendit: {
    icon: CreditCard,
    label: 'Prepaid credits',
    color: 'text-violet-600 dark:text-violet-400',
    bgColor: 'bg-violet-50 dark:bg-violet-950/30',
    borderColor: 'border-violet-200 dark:border-violet-800',
    description: 'Top up credits to use this endpoint.'
  },
  stripe: {
    icon: CreditCard,
    label: 'Prepaid credits',
    color: 'text-indigo-600 dark:text-indigo-400',
    bgColor: 'bg-indigo-50 dark:bg-indigo-950/30',
    borderColor: 'border-indigo-200 dark:border-indigo-800',
    description: 'Top up credits to use this endpoint.'
  },
  // Access control policies
  public: {
    icon: Globe,
    label: 'Public Access',
    color: 'text-sky-600 dark:text-sky-400',
    bgColor: 'bg-sky-50 dark:bg-sky-950/30',
    borderColor: 'border-sky-200 dark:border-sky-800',
    description: 'Anyone can access this endpoint without authentication'
  },
  private: {
    icon: Lock,
    label: 'Private Access',
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-50 dark:bg-red-950/30',
    borderColor: 'border-red-200 dark:border-red-800',
    description: 'Only the owner can access this endpoint'
  },
  authenticated: {
    icon: Key,
    label: 'Authentication Required',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-50 dark:bg-amber-950/30',
    borderColor: 'border-amber-200 dark:border-amber-800',
    description: 'Requires authentication to access'
  },
  internal: {
    icon: Shield,
    label: 'Internal Only',
    color: 'text-indigo-600 dark:text-indigo-400',
    bgColor: 'bg-indigo-50 dark:bg-indigo-950/30',
    borderColor: 'border-indigo-200 dark:border-indigo-800',
    description: 'Only accessible to the owner'
  },
  // Rate limiting and quotas
  rate_limit: {
    icon: Gauge,
    label: 'Rate Limit',
    color: 'text-orange-600 dark:text-orange-400',
    bgColor: 'bg-orange-50 dark:bg-orange-950/30',
    borderColor: 'border-orange-200 dark:border-orange-800',
    description: 'Request rate is limited'
  },
  quota: {
    icon: Zap,
    label: 'Usage Quota',
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-50 dark:bg-purple-950/30',
    borderColor: 'border-purple-200 dark:border-purple-800',
    description: 'Usage quota applies to this endpoint'
  },
  // Geographic restrictions
  geographic: {
    icon: MapPin,
    label: 'Geographic Restriction',
    color: 'text-rose-600 dark:text-rose-400',
    bgColor: 'bg-rose-50 dark:bg-rose-950/30',
    borderColor: 'border-rose-200 dark:border-rose-800',
    description: 'Access restricted by geographic location'
  }
};

const DEFAULT_POLICY_CONFIG = {
  icon: ShieldCheck,
  label: 'Policy',
  color: 'text-slate-600 dark:text-slate-400',
  bgColor: 'bg-slate-50 dark:bg-slate-950/30',
  borderColor: 'border-slate-200 dark:border-slate-800',
  description: 'Custom policy configuration'
};

function getPolicyConfig(type: string) {
  return POLICY_TYPE_CONFIG[type.toLowerCase()] ?? DEFAULT_POLICY_CONFIG;
}

export interface PolicyItemProperties {
  policy: Policy;
  endpointSlug?: string;
  endpointOwner?: string;
}

function renderPolicyContent(
  policy: Policy,
  prepaidProvider: PrepaidProvider | null,
  endpointSlug?: string,
  endpointOwner?: string
): React.ReactElement {
  if (prepaidProvider) {
    return (
      <XenditPolicyContent
        provider={prepaidProvider}
        config={policy.config}
        enabled={policy.enabled}
        endpointSlug={endpointSlug}
        endpointOwner={endpointOwner}
      />
    );
  }
  return <GenericPolicyContent config={policy.config} />;
}

interface BalancePolicyCardProperties {
  policy: Policy;
  config: ReturnType<typeof getPolicyConfig>;
  displayLabel: string;
  description: string | null;
  providerLabel: string | null;
  prepaidProvider: PrepaidProvider | null;
  isMpp: boolean;
  endpointSlug?: string;
  endpointOwner?: string;
}

/**
 * Premium block-card layout shared by prepaid-credits and pay-as-you-go (MPP)
 * policies: neutral card with an icon chip, "via <provider>" sub-header, an
 * Active/Disabled status pill, and a "How does this work?" accordion. The body
 * differs per kind — prepaid shows a bundle picker + Buy CTA, MPP shows the
 * automatic per-request price.
 */
function BalancePolicyCard({
  policy,
  config,
  displayLabel,
  description,
  providerLabel,
  prepaidProvider,
  isMpp,
  endpointSlug,
  endpointOwner
}: Readonly<BalancePolicyCardProperties>) {
  const Icon = config.icon;
  // Prepaid surfaces its price in the header; MPP renders it inside the body
  // (MppPolicyContent), so this is parsed for prepaid only.
  const prepaidParsed = useMemo(
    () => (prepaidProvider ? parseXenditConfig(policy.config) : null),
    [prepaidProvider, policy.config]
  );
  const prepaidPricePerUnit =
    prepaidParsed && prepaidParsed.pricePerUnit !== null && prepaidParsed.pricePerUnit > 0
      ? prepaidParsed.pricePerUnit
      : null;

  return (
    <div
      className={cn(
        'group bg-card relative rounded-lg border transition-colors transition-shadow duration-200',
        'border-border',
        policy.enabled ? 'hover:shadow-md hover:shadow-black/5' : 'opacity-60 grayscale-[30%]'
      )}
    >
      <div className='p-4'>
        <div className='flex items-start gap-3'>
          <div
            className={cn(
              'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
              config.bgColor,
              'ring-1 ring-inset',
              config.borderColor
            )}
          >
            <Icon className={cn('h-4.5 w-4.5', config.color)} />
          </div>

          <div className='min-w-0 flex-1'>
            <div className='flex items-start justify-between gap-2'>
              <div className='min-w-0'>
                <h3 className='text-foreground text-sm leading-tight font-semibold'>
                  {displayLabel}
                </h3>
                <p className='text-muted-foreground mt-0.5 text-[11px]'>via {providerLabel}</p>
              </div>
              {policy.version ? (
                <span className='text-muted-foreground bg-muted/60 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium tabular-nums'>
                  v{policy.version}
                </span>
              ) : null}
            </div>

            <div className='mt-1.5 flex items-center gap-1.5'>
              <span
                aria-hidden='true'
                className={cn(
                  'inline-block h-1.5 w-1.5 rounded-full',
                  policy.enabled ? 'bg-emerald-500' : 'bg-muted-foreground/40'
                )}
              />
              <span
                className={cn(
                  'text-[11px] font-medium',
                  policy.enabled
                    ? 'text-emerald-700 dark:text-emerald-400'
                    : 'text-muted-foreground'
                )}
              >
                {policy.enabled ? 'Active' : 'Disabled'}
              </span>
            </div>

            {description && (
              <p className='text-muted-foreground mt-2 text-xs leading-relaxed'>{description}</p>
            )}
            {prepaidParsed && prepaidPricePerUnit !== null && (
              <p className='text-muted-foreground mt-0.5 text-[11px] tabular-nums'>
                {prepaidParsed.currency} {prepaidPricePerUnit.toLocaleString()} per{' '}
                {UNIT_LABEL[prepaidParsed.unit].singular}
              </p>
            )}

            {Object.keys(policy.config).length > 0 &&
              (isMpp ? (
                <MppPolicyContent config={policy.config} />
              ) : (
                // Reached only for prepaid (isMpp is handled above).
                renderPolicyContent(policy, prepaidProvider, endpointSlug, endpointOwner)
              ))}
          </div>
        </div>
      </div>

      <div className='border-border/60 border-t'>
        {isMpp ? (
          <HowItWorksAccordion>
            Pay-as-you-go billing is automatic — there is nothing to top up. Whenever a request is
            processed, the price per request shown above is deducted from your available MPP wallet
            balance. Keep your wallet funded to keep making requests.
          </HowItWorksAccordion>
        ) : (
          <HowItWorksAccordion>
            Purchase credits upfront with a data owner. Your balance is shared across all of their
            endpoints. Top up anytime — credits are deducted per request until your balance runs
            out.
          </HowItWorksAccordion>
        )}
      </div>
    </div>
  );
}

// Single policy item component - memoized to prevent unnecessary re-renders
export const PolicyItem = memo(function PolicyItem({
  policy,
  endpointSlug,
  endpointOwner
}: Readonly<PolicyItemProperties>) {
  const config = getPolicyConfig(policy.type);
  const Icon = config.icon;
  const policyTypeLower = policy.type.toLowerCase();
  const prepaidProvider: PrepaidProvider | null = isPrepaidBalanceType(policyTypeLower)
    ? policyTypeLower
    : null;
  const isMpp = isMppBalanceType(policyTypeLower);
  // Both prepaid and pay-as-you-go render the same premium block card; only the
  // body (bundle picker vs. price-per-request) and the accordion copy differ.
  const usesBalanceCard = Boolean(prepaidProvider) || isMpp;
  // Provider-agnostic display name surfaced under the card title (e.g. "via
  // Xendit", "via Tempo").
  const providerLabel = getBalanceProviderLabel(policyTypeLower);

  // For unknown policy types, use the type as the label
  const displayLabel = POLICY_TYPE_CONFIG[policy.type.toLowerCase()]
    ? config.label
    : formatConfigKey(policy.type);

  // Avoid printing the description when it just repeats the visible label
  // (e.g. publisher set policy.name = type label).
  const rawDescription = policy.description || config.description;
  const description = rawDescription && rawDescription !== displayLabel ? rawDescription : null;

  if (usesBalanceCard) {
    return (
      <BalancePolicyCard
        policy={policy}
        config={config}
        displayLabel={displayLabel}
        description={description}
        providerLabel={providerLabel}
        prepaidProvider={prepaidProvider}
        isMpp={isMpp}
        endpointSlug={endpointSlug}
        endpointOwner={endpointOwner}
      />
    );
  }

  return (
    <div
      className={cn(
        'group relative rounded-lg border p-4 transition-colors transition-shadow duration-200',
        config.borderColor,
        config.bgColor,
        policy.enabled ? 'hover:shadow-md hover:shadow-black/5' : 'opacity-60 grayscale-[30%]'
      )}
    >
      <div className='flex items-start gap-3'>
        {/* Icon */}
        <div
          className={cn(
            'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
            config.bgColor,
            'ring-1 ring-inset',
            config.borderColor
          )}
        >
          <Icon className={cn('h-4.5 w-4.5', config.color)} />
        </div>

        {/* Content */}
        <div className='min-w-0 flex-1'>
          <div className='flex items-center justify-between gap-2'>
            <span className={cn('text-sm font-semibold', config.color)}>{displayLabel}</span>
            <Badge
              variant='outline'
              className={cn(
                'shrink-0 text-[10px] font-medium',
                policy.enabled
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400'
                  : 'border-border bg-muted text-muted-foreground'
              )}
            >
              {policy.enabled ? 'Active' : 'Disabled'}
            </Badge>
          </div>
          {description && <p className='text-muted-foreground mt-1 text-xs'>{description}</p>}

          {/* Policy-specific content */}
          {Object.keys(policy.config).length > 0 &&
            renderPolicyContent(policy, prepaidProvider, endpointSlug, endpointOwner)}

          {policy.version ? (
            <div className='mt-2'>
              <p className='text-muted-foreground text-[10px]'>Version {policy.version}</p>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
});

// Shared "How does this work?" accordion for the balance cards. Only the body
// copy differs between prepaid and pay-as-you-go, so the chrome lives here once.
function HowItWorksAccordion({ children }: Readonly<{ children: React.ReactNode }>) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger
        className={cn(
          'text-muted-foreground hover:text-foreground hover:bg-muted/40 flex w-full cursor-pointer items-center justify-between gap-2 rounded-b-lg px-4 py-2.5',
          'focus-visible:bg-muted/40 focus-visible:text-foreground focus-visible:outline-none',
          'transition-colors select-none'
        )}
      >
        <span className='inline-flex items-center gap-1.5 text-[11px] font-medium'>
          <Info className='h-3 w-3' aria-hidden='true' />
          How does this work?
        </span>
        <ChevronDown
          className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')}
          aria-hidden='true'
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <p className='text-muted-foreground border-border/60 max-w-prose border-t px-4 py-3 text-[11px] leading-relaxed'>
          {children}
        </p>
      </CollapsibleContent>
    </Collapsible>
  );
}
