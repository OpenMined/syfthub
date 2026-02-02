/**
 * SuggestionItem Component
 *
 * Displays a selectable source suggestion in the autocomplete dropdown.
 * Shows source name, path, and selection state.
 */
import type { ChatSource } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';

// =============================================================================
// Types
// =============================================================================

export interface SuggestionItemProps {
  source: ChatSource;
  isSelected: boolean;
  onSelect: () => void;
}

// =============================================================================
// Component
// =============================================================================

export function SuggestionItem({ source, isSelected, onSelect }: Readonly<SuggestionItemProps>) {
  return (
    <button
      type='button'
      onClick={onSelect}
      className='hover:bg-accent flex w-full items-center gap-2 px-3 py-2 text-left first:rounded-t-lg last:rounded-b-lg'
    >
      <div className='font-inter flex h-6 w-6 shrink-0 items-center justify-center rounded bg-green-100 text-[10px] font-bold text-green-700'>
        {source.name.slice(0, 2).toUpperCase()}
      </div>
      <div className='min-w-0 flex-1'>
        <span className='font-inter text-foreground block truncate text-xs font-medium'>
          {source.name}
        </span>
        <span className='font-inter text-muted-foreground truncate text-[10px]'>
          {source.full_path}
        </span>
      </div>
      {isSelected && <Check className='h-3 w-3 text-green-600' />}
    </button>
  );
}
