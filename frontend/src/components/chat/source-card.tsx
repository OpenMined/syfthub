/**
 * SourceCard Component
 *
 * Displays a selected data source as a card with cost badges and a remove button.
 * Used in the advanced panel to show active data sources.
 */
import type { ChatSource } from '@/lib/types';

import X from 'lucide-react/dist/esm/icons/x';

import { getCostsFromSource } from '@/lib/cost-utils';

import { CostBadges } from './cost-badges';

// =============================================================================
// Types
// =============================================================================

export interface SourceCardProps {
  source: ChatSource;
  onRemove: () => void;
}

// =============================================================================
// Component
// =============================================================================

export function SourceCard({ source, onRemove }: Readonly<SourceCardProps>) {
  const costs = getCostsFromSource(source);

  return (
    <div className='group bg-card relative rounded-lg border border-green-100 p-3 shadow-sm dark:border-green-800'>
      <button
        onClick={onRemove}
        className='absolute top-2 right-2 rounded p-1 text-red-500 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-red-50 dark:hover:bg-red-950'
        aria-label={`Remove ${source.name}`}
      >
        <X className='h-3 w-3' aria-hidden='true' />
      </button>
      <div className='mb-3 flex items-center gap-3'>
        <div className='font-inter flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-green-100 text-xs font-bold text-green-700 dark:bg-green-900 dark:text-green-300'>
          {source.name.slice(0, 2).toUpperCase() || '??'}
        </div>
        <div className='min-w-0 flex-1'>
          <span
            className='font-inter text-foreground block truncate text-sm font-medium'
            title={source.name}
          >
            {source.name}
          </span>
          {source.full_path && (
            <span className='font-inter text-muted-foreground truncate text-xs'>
              {source.full_path}
            </span>
          )}
        </div>
      </div>
      <div className='flex flex-wrap gap-2'>
        <CostBadges
          inputPerToken={costs.inputPerToken}
          outputPerToken={costs.outputPerToken}
          colorScheme='green'
          pricingMode={costs.pricingMode}
          pricePerCall={costs.pricePerCall}
        />
      </div>
    </div>
  );
}
