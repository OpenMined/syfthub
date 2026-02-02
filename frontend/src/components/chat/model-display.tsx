/**
 * ModelDisplay Component
 *
 * Displays the selected model's details including name, version,
 * cost badges, and the current reasoning mode description.
 */
import type { ChatSource } from '@/lib/types';

import Brain from 'lucide-react/dist/esm/icons/brain';
import Info from 'lucide-react/dist/esm/icons/info';

import { CostBadges } from './cost-badges';

// =============================================================================
// Types
// =============================================================================

export interface ModelDisplayProps {
  model: ChatSource | null;
  modelCosts: { inputPerToken: number; outputPerToken: number } | null;
  isFactualMode: boolean;
}

// =============================================================================
// Component
// =============================================================================

export function ModelDisplay({ model, modelCosts, isFactualMode }: Readonly<ModelDisplayProps>) {
  if (!model) {
    return (
      <div className='font-inter bg-card/50 rounded-lg border border-dashed border-purple-200 py-6 text-center text-sm text-purple-700/50 dark:border-purple-800 dark:text-purple-400/50'>
        <p>No model selected</p>
        <p className='mt-1 text-xs'>Select a model from the dropdown above</p>
      </div>
    );
  }

  return (
    <>
      <div className='flex items-center gap-3'>
        <div className='flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300'>
          <Brain className='h-4 w-4' />
        </div>
        <div className='min-w-0 flex-1'>
          <span
            className='font-inter text-foreground block truncate text-sm font-medium'
            title={model.name}
          >
            {model.name}
          </span>
          <span className='font-inter text-muted-foreground text-xs'>
            {model.version ? `v${model.version}` : 'latest'}
          </span>
        </div>
      </div>
      <div className='flex flex-wrap gap-2'>
        <CostBadges
          inputPerToken={modelCosts?.inputPerToken ?? 0}
          outputPerToken={modelCosts?.outputPerToken ?? 0}
          colorScheme='purple'
        />
      </div>
      <div
        id='mode-description'
        className='font-inter text-muted-foreground mt-2 flex items-start gap-2 border-t border-purple-50 pt-2 text-xs dark:border-purple-900'
      >
        <Info className='mt-0.5 h-3 w-3 shrink-0' aria-hidden='true' />
        {isFactualMode
          ? 'Strict mode: Results will be grounded in retrieved data only.'
          : 'Nuanced mode: Model can infer and synthesize broader context.'}
      </div>
    </>
  );
}
