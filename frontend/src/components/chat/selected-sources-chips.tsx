import { memo, useCallback } from 'react';

import type { ChatSource } from '@/lib/types';

import Database from 'lucide-react/dist/esm/icons/database';
import X from 'lucide-react/dist/esm/icons/x';

// ============================================================================
// Main Component
// ============================================================================

export interface SelectedSourcesChipsProps {
  sources: ChatSource[];
  onRemove: (id: string) => void;
  onEdit: () => void;
}

export const SelectedSourcesChips = memo(function SelectedSourcesChips({
  sources,
  onRemove,
  onEdit
}: Readonly<SelectedSourcesChipsProps>) {
  const handleRemove = useCallback(
    (id: string) => {
      onRemove(id);
    },
    [onRemove]
  );

  if (sources.length === 0) return null;

  return (
    <div className='mb-2 flex flex-wrap items-center gap-2'>
      {sources.map((source) => (
        <span
          key={source.id}
          className='font-inter inline-flex items-center gap-1.5 rounded-full border border-green-200 bg-green-50 px-3 py-1 text-xs font-medium text-green-700 dark:border-green-800 dark:bg-green-950/30 dark:text-green-300'
        >
          <Database className='h-3 w-3' aria-hidden='true' />
          <span className='max-w-[140px] truncate'>{source.name}</span>
          <button
            type='button'
            onClick={() => {
              handleRemove(source.id);
            }}
            className='-mr-1 ml-0.5 rounded-full p-0.5 text-green-500 transition-colors hover:text-green-700 dark:hover:text-green-100'
            aria-label={`Remove ${source.name}`}
          >
            <X className='h-3 w-3' />
          </button>
        </span>
      ))}
      <button
        type='button'
        onClick={onEdit}
        className='font-inter text-muted-foreground hover:text-foreground text-xs transition-colors'
      >
        Edit
      </button>
    </div>
  );
});
