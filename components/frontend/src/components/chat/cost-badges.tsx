/**
 * CostBadges Component
 *
 * Displays input/output cost badges for data sources and models.
 * Shows formatted per-unit pricing with color-coded badges.
 */
import type { PricingMode } from '@/lib/cost-utils';

import { Badge } from '@/components/ui/badge';
import { formatCostPerUnit } from '@/lib/cost-utils';

// =============================================================================
// Types
// =============================================================================

export interface CostBadgesProps {
  inputPerToken: number;
  outputPerToken: number;
  colorScheme: 'green' | 'purple';
  pricingMode?: PricingMode;
  pricePerCall?: number;
}

// =============================================================================
// Component
// =============================================================================

export function CostBadges({
  inputPerToken,
  outputPerToken,
  colorScheme,
  pricingMode,
  pricePerCall
}: Readonly<CostBadgesProps>) {
  const colorClasses =
    colorScheme === 'green'
      ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950 dark:text-green-300'
      : 'border-purple-200 bg-purple-50 text-purple-700 dark:border-purple-800 dark:bg-purple-950 dark:text-purple-300';

  // Per-call pricing: show a single badge with flat price
  if (pricingMode === 'per_call' && pricePerCall != null && pricePerCall > 0) {
    return (
      <Badge
        variant='secondary'
        className={`font-inter h-5 px-2 text-[10px] font-medium ${colorClasses}`}
      >
        {formatCostPerUnit(pricePerCall, 'call')}
      </Badge>
    );
  }

  const hasInputCost = inputPerToken > 0;
  const hasOutputCost = outputPerToken > 0;

  if (!hasInputCost && !hasOutputCost) {
    return (
      <Badge
        variant='secondary'
        className='font-inter border-border bg-muted text-muted-foreground h-5 px-2 text-[10px] font-normal'
      >
        No pricing
      </Badge>
    );
  }

  return (
    <>
      {hasInputCost && (
        <Badge
          variant='secondary'
          className={`font-inter h-5 px-2 text-[10px] font-medium ${colorClasses}`}
        >
          In: {formatCostPerUnit(inputPerToken, 'request')}
        </Badge>
      )}
      {hasOutputCost && (
        <Badge
          variant='secondary'
          className={`font-inter h-5 px-2 text-[10px] font-medium ${colorClasses}`}
        >
          Out: {formatCostPerUnit(outputPerToken, 'request')}
        </Badge>
      )}
    </>
  );
}
