import { useMemo } from 'react';

import type { ChatSource } from '@/lib/types';

import { motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Coins from 'lucide-react/dist/esm/icons/coins';

import { calculateFullCostBreakdown, formatCurrency } from '@/lib/cost-utils';

interface CostEstimationPanelProps {
  model: ChatSource | null;
  dataSources: ChatSource[];
}

// Fixed estimation: 1K tokens for input and output
const FIXED_ESTIMATION = {
  estimatedInputTokens: 1000,
  estimatedOutputTokens: 1000,
  queriesPerSource: 1
};

export function CostEstimationPanel({ model, dataSources }: Readonly<CostEstimationPanelProps>) {
  const breakdown = useMemo(
    () => calculateFullCostBreakdown(model, dataSources, FIXED_ESTIMATION),
    [model, dataSources]
  );

  const hasModel = Boolean(model);
  const hasDataSources = dataSources.length > 0;

  // Empty state
  if (!hasModel && !hasDataSources) {
    return (
      <div className='border-border bg-muted/50 rounded-lg border border-dashed py-6 text-center'>
        <Coins className='text-muted-foreground mx-auto h-6 w-6' />
        <p className='font-inter text-muted-foreground mt-2 text-xs'>
          Select a model and data sources to see cost estimates
        </p>
      </div>
    );
  }

  return (
    <div className='relative overflow-hidden rounded-xl border border-blue-200 bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 p-4 dark:border-blue-800 dark:from-blue-950/40 dark:via-indigo-950/40 dark:to-purple-950/40'>
      {/* Decorative elements */}
      <div className='absolute top-0 right-0 h-20 w-20 translate-x-6 -translate-y-6 rounded-full bg-blue-200/30 blur-2xl dark:bg-blue-800/30' />
      <div className='absolute bottom-0 left-0 h-16 w-16 -translate-x-4 translate-y-4 rounded-full bg-purple-200/30 blur-xl dark:bg-purple-800/30' />

      <div className='relative'>
        <div className='mb-3 flex items-center gap-2'>
          <div className='flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 shadow-lg shadow-blue-500/25 dark:from-blue-600 dark:to-indigo-700 dark:shadow-blue-600/20'>
            <Coins className='h-3.5 w-3.5 text-white' />
          </div>
          <span className='font-inter text-xs font-semibold text-blue-900 dark:text-blue-300'>
            Estimated Cost{' '}
            <span className='font-normal text-blue-700 dark:text-blue-400'>(per 1K tokens)</span>
          </span>
        </div>

        {/* Cost breakdown: Input / Output / Total */}
        <div className='space-y-2'>
          {/* Input Cost */}
          <div className='flex items-center justify-between'>
            <span className='font-inter text-muted-foreground text-xs'>Input</span>
            <motion.span
              key={`input-${String(breakdown.totalInputCost)}`}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              className='text-foreground font-mono text-sm font-medium tabular-nums'
            >
              {formatCurrency(breakdown.totalInputCost)}
            </motion.span>
          </div>

          {/* Output Cost */}
          <div className='flex items-center justify-between'>
            <span className='font-inter text-muted-foreground text-xs'>Output</span>
            <motion.span
              key={`output-${String(breakdown.totalOutputCost)}`}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              className='text-foreground font-mono text-sm font-medium tabular-nums'
            >
              {formatCurrency(breakdown.totalOutputCost)}
            </motion.span>
          </div>

          {/* Divider */}
          <div className='border-t border-blue-200/50 dark:border-blue-800/50' />

          {/* Total */}
          <div className='flex items-center justify-between'>
            <span className='font-inter text-foreground text-xs font-semibold'>Total</span>
            <motion.span
              key={`total-${String(breakdown.totalCost)}`}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              className='text-foreground font-mono text-lg font-bold tabular-nums'
            >
              {formatCurrency(breakdown.totalCost)}
            </motion.span>
          </div>
        </div>

        {breakdown.hasAnyPricing ? null : (
          <div className='mt-3 flex items-center gap-1.5 text-[10px] text-amber-600 dark:text-amber-400'>
            <AlertCircle className='h-3 w-3' />
            <span>Some endpoints have no pricing configured</span>
          </div>
        )}
      </div>
    </div>
  );
}
