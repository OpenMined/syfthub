/**
 * SourceSelector Component
 *
 * Two side-by-side dropdown trigger buttons for selecting the model mode
 * ("Auto") and source filter ("All Sources"). Uses the existing DropdownMenu
 * Radix implementation. Designed to sit inside the SearchInput bottom toolbar.
 */

import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

// =============================================================================
// Types
// =============================================================================

export interface SourceSelectorProps {
  /** Current model mode (e.g., "auto", "manual") */
  mode: string;
  /** Callback when model mode changes */
  onModeChange: (mode: string) => void;
  /** Current source filter (e.g., "all", "selected") */
  sourceFilter: string;
  /** Callback when source filter changes */
  onSourceFilterChange: (filter: string) => void;
  /** Whether the selector is disabled */
  disabled?: boolean;
  /** Additional CSS classes */
  className?: string;
}

// =============================================================================
// Constants
// =============================================================================

const MODE_OPTIONS = [
  { value: 'auto', label: 'Auto' },
  { value: 'manual', label: 'Manual' }
] as const;

const SOURCE_OPTIONS = [
  { value: 'all', label: 'All Sources' },
  { value: 'selected', label: 'Selected Only' }
] as const;

const MODE_LABELS: Record<string, string> = {
  auto: 'Auto',
  manual: 'Manual'
};

const SOURCE_LABELS: Record<string, string> = {
  all: 'All Sources',
  selected: 'Selected Only'
};

// =============================================================================
// Component
// =============================================================================

/**
 * Two inline dropdown buttons for model mode and source filter selection.
 *
 * @example
 * ```tsx
 * <SourceSelector
 *   mode="auto"
 *   onModeChange={setMode}
 *   sourceFilter="all"
 *   onSourceFilterChange={setSourceFilter}
 * />
 * ```
 */
export function SourceSelector({
  mode,
  onModeChange,
  sourceFilter,
  onSourceFilterChange,
  disabled,
  className
}: Readonly<SourceSelectorProps>) {
  return (
    <div className={cn('flex items-center gap-1', className)}>
      {/* Mode Dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger
          disabled={disabled}
          className='text-muted-foreground hover:text-foreground hover:bg-accent inline-flex h-9 items-center gap-1 rounded-lg px-2.5 text-sm font-normal transition-colors focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50'
        >
          {MODE_LABELS[mode] ?? mode}
          <ChevronDown className='h-3.5 w-3.5' aria-hidden='true' />
        </DropdownMenuTrigger>
        <DropdownMenuContent align='start' side='top'>
          {MODE_OPTIONS.map((option) => (
            <DropdownMenuItem
              key={option.value}
              onSelect={() => {
                onModeChange(option.value);
              }}
            >
              {option.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Source Filter Dropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger
          disabled={disabled}
          className='text-muted-foreground hover:text-foreground hover:bg-accent inline-flex h-9 items-center gap-1 rounded-lg px-2.5 text-sm font-normal transition-colors focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50'
        >
          {SOURCE_LABELS[sourceFilter] ?? sourceFilter}
          <ChevronDown className='h-3.5 w-3.5' aria-hidden='true' />
        </DropdownMenuTrigger>
        <DropdownMenuContent align='start' side='top'>
          {SOURCE_OPTIONS.map((option) => (
            <DropdownMenuItem
              key={option.value}
              onSelect={() => {
                onSourceFilterChange(option.value);
              }}
            >
              {option.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
