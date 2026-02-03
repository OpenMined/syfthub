import { memo, useCallback } from 'react';

import type { ChatSource } from '@/lib/types';

import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import Database from 'lucide-react/dist/esm/icons/database';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import X from 'lucide-react/dist/esm/icons/x';
import { Link, useNavigate } from 'react-router-dom';

import { useContextSelectionStore } from '@/stores/context-selection-store';

// ============================================================================
// Sub-components
// ============================================================================

interface ContextChipProps {
  source: ChatSource;
  onRemove: (id: string) => void;
}

const ContextChip = memo(function ContextChip({ source, onRemove }: Readonly<ContextChipProps>) {
  const detailHref = source.owner_username
    ? `/${source.owner_username}/${source.slug}`
    : `/browse/${source.slug}`;

  return (
    <div className='border-border bg-background flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 shadow-sm'>
      <Database className='text-primary h-3.5 w-3.5 shrink-0' aria-hidden='true' />
      <span className='font-inter text-foreground max-w-[140px] truncate text-xs font-medium'>
        {source.name}
      </span>
      <Link
        to={detailHref}
        className='text-muted-foreground hover:text-foreground shrink-0 transition-colors'
        aria-label={`View ${source.name} details`}
        onClick={(e) => {
          e.stopPropagation();
        }}
      >
        <ExternalLink className='h-3 w-3' />
      </Link>
      <button
        type='button'
        onClick={() => {
          onRemove(source.id);
        }}
        className='text-muted-foreground hover:text-foreground shrink-0 transition-colors'
        aria-label={`Remove ${source.name} from context`}
      >
        <X className='h-3 w-3' />
      </button>
    </div>
  );
});

// ============================================================================
// Main Component
// ============================================================================

export const ContextBar = memo(function ContextBar() {
  const selectedSources = useContextSelectionStore((s) => s.selectedSources);
  const removeSource = useContextSelectionStore((s) => s.removeSource);
  const clearSources = useContextSelectionStore((s) => s.clearSources);
  const navigate = useNavigate();

  const sourcesArray = [...selectedSources.values()];
  const count = sourcesArray.length;

  const handleRemove = useCallback(
    (id: string) => {
      removeSource(id);
    },
    [removeSource]
  );

  const handleStartChat = useCallback(() => {
    // eslint-disable-next-line @typescript-eslint/no-floating-promises -- Navigation is fire-and-forget
    navigate('/chat', {
      state: {
        contextSources: sourcesArray
      }
    });
    clearSources();
  }, [navigate, sourcesArray, clearSources]);

  if (count === 0) return null;

  return (
    <div className='fixed bottom-0 left-0 z-50 w-full pl-20'>
      <div className='border-border bg-card/95 mx-auto max-w-4xl rounded-t-2xl border border-b-0 px-5 py-3.5 shadow-lg backdrop-blur-sm'>
        <div className='flex items-center gap-4'>
          {/* Label */}
          <span className='font-rubik text-muted-foreground shrink-0 text-[10px] font-semibold tracking-widest uppercase'>
            Your Context
          </span>

          {/* Chips */}
          <div className='flex min-w-0 flex-1 items-center gap-2 overflow-x-auto'>
            {sourcesArray.map((source) => (
              <ContextChip key={source.id} source={source} onRemove={handleRemove} />
            ))}
          </div>

          {/* Start Chat Button */}
          <button
            type='button'
            onClick={handleStartChat}
            className='bg-primary text-primary-foreground hover:bg-primary/90 font-inter flex shrink-0 items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors'
          >
            Start Chat
            <ArrowRight className='h-4 w-4' aria-hidden='true' />
          </button>
        </div>
      </div>
    </div>
  );
});
