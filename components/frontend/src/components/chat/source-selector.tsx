/**
 * SourceSelector Component
 *
 * Dropdown trigger button for selecting a source filter ("All Sources" / "Selected Only").
 * Uses the existing DropdownMenu Radix implementation.
 * Designed to sit inside the SearchInput bottom toolbar.
 */

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

const SOURCE_OPTIONS = [
  { value: 'all', label: 'All Sources' },
  { value: 'selected', label: 'Selected Only' }
] as const;

const SOURCE_LABELS: Record<string, string> = {
  all: 'All Sources',
  selected: 'Selected Only'
};

// =============================================================================
// Component
// =============================================================================

/**
 * Inline dropdown button for source filter selection.
 *
 * @example
 * ```tsx
 * <SourceSelector
 *   sourceFilter="all"
 *   onSourceFilterChange={setSourceFilter}
 * />
 * ```
 */
export function SourceSelector({
  sourceFilter,
  onSourceFilterChange,
  disabled,
  className
}: Readonly<SourceSelectorProps>) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled}
        className={cn(
          'text-muted-foreground hover:text-foreground hover:bg-accent inline-flex h-9 items-center gap-1 rounded-lg px-2.5 text-sm font-normal transition-colors focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50',
          className
        )}
      >
        {SOURCE_LABELS[sourceFilter] ?? sourceFilter}
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
  );
}
