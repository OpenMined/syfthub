import React, { memo } from 'react';

import { formatConfigKey, formatCost } from './transaction-policy-content';

// Render config value based on type
// eslint-disable-next-line sonarjs/function-return-type -- Different JSX elements are all valid React.ReactNode
function renderConfigValue(value: unknown, key: string): React.ReactNode {
  if (value === null || value === undefined)
    return <span className='text-muted-foreground'>—</span>;
  if (typeof value === 'boolean') {
    return value ? (
      <span className='text-emerald-600'>Yes</span>
    ) : (
      <span className='text-muted-foreground'>No</span>
    );
  }
  if (typeof value === 'number') {
    // Check if it looks like a cost value
    if (key.includes('token') || key.includes('cost')) {
      return <span className='font-mono'>{formatCost(value, 'token')}</span>;
    }
    if (key.includes('query') || key.includes('retrieval')) {
      return <span className='font-mono'>{formatCost(value, 'query')}</span>;
    }
    return <span className='font-mono'>{value.toLocaleString()}</span>;
  }
  if (typeof value === 'string') {
    return <span>{value}</span>;
  }
  // Handle objects, arrays, and any other types via JSON serialization
  return <span className='font-mono text-[10px]'>{JSON.stringify(value)}</span>;
}

export interface GenericPolicyContentProperties {
  config: Record<string, unknown>;
}

// Generic config renderer for unknown policy types - memoized to prevent unnecessary re-renders
export const GenericPolicyContent = memo(function GenericPolicyContent({
  config
}: Readonly<GenericPolicyContentProperties>) {
  const entries = Object.entries(config).filter(
    ([, value]) => value !== null && value !== undefined && value !== ''
  );

  if (entries.length === 0) return null;

  return (
    <div className='mt-3'>
      <div className='border-border bg-card/60 rounded-md border'>
        <div className='border-border border-b px-3 py-1.5'>
          <span className='text-muted-foreground text-[10px] font-semibold tracking-wide uppercase'>
            Configuration
          </span>
        </div>
        <div className='divide-border divide-y'>
          {entries.map(([key, value]) => (
            <div key={key} className='flex items-center justify-between gap-2 px-3 py-1.5'>
              <span className='text-muted-foreground shrink-0 text-xs'>{formatConfigKey(key)}</span>
              <span className='text-foreground truncate text-xs'>
                {renderConfigValue(value, key)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
});
