import React, { memo } from 'react';

import type { Policy } from '@/lib/types';

import Coins from 'lucide-react/dist/esm/icons/coins';
import CreditCard from 'lucide-react/dist/esm/icons/credit-card';
import Gauge from 'lucide-react/dist/esm/icons/gauge';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Key from 'lucide-react/dist/esm/icons/key';
import Lock from 'lucide-react/dist/esm/icons/lock';
import MapPin from 'lucide-react/dist/esm/icons/map-pin';
import Shield from 'lucide-react/dist/esm/icons/shield';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import Zap from 'lucide-react/dist/esm/icons/zap';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

import { BundleSubscriptionPolicyContent } from './bundle-subscription-policy-content';
import { GenericPolicyContent } from './generic-policy-content';
import { formatConfigKey, TransactionPolicyContent } from './transaction-policy-content';

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
  // Transaction/Pricing policies
  transaction: {
    icon: Coins,
    label: 'Transaction Policy',
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-50 dark:bg-emerald-950/30',
    borderColor: 'border-emerald-200 dark:border-emerald-800',
    description: 'Pay-per-use pricing for this endpoint'
  },
  bundle_subscription: {
    icon: CreditCard,
    label: 'Bundle Subscription',
    color: 'text-violet-600 dark:text-violet-400',
    bgColor: 'bg-violet-50 dark:bg-violet-950/30',
    borderColor: 'border-violet-200 dark:border-violet-800',
    description: 'Subscription required to access this endpoint'
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
    description: 'Only accessible within the organization'
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
}

function renderPolicyContent(
  policy: Policy,
  isTransaction: boolean,
  isBundleSubscription: boolean
): React.ReactElement {
  if (isTransaction) {
    return <TransactionPolicyContent config={policy.config} />;
  }
  if (isBundleSubscription) {
    return <BundleSubscriptionPolicyContent config={policy.config} enabled={policy.enabled} />;
  }
  return <GenericPolicyContent config={policy.config} />;
}

// Single policy item component - memoized to prevent unnecessary re-renders
export const PolicyItem = memo(function PolicyItem({ policy }: Readonly<PolicyItemProperties>) {
  const config = getPolicyConfig(policy.type);
  const Icon = config.icon;
  const policyTypeLower = policy.type.toLowerCase();
  const isTransaction = policyTypeLower === 'transaction';
  const isBundleSubscription = policyTypeLower === 'bundle_subscription';

  // For unknown policy types, use the type as the label
  const displayLabel = POLICY_TYPE_CONFIG[policy.type.toLowerCase()]
    ? config.label
    : formatConfigKey(policy.type);

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
          <p className='text-muted-foreground mt-1 text-xs'>
            {policy.description || config.description}
          </p>

          {/* Policy-specific content */}
          {Object.keys(policy.config).length > 0 &&
            renderPolicyContent(policy, isTransaction, isBundleSubscription)}

          {policy.version ? (
            <p className='text-muted-foreground mt-2 text-[10px]'>Version {policy.version}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
});
