/**
 * ContextPill Component
 *
 * Small pill-shaped button displaying "@ Add context" that opens
 * a context/mention picker. Used inside the SearchInput toolbar.
 */

import AtSign from 'lucide-react/dist/esm/icons/at-sign';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// =============================================================================
// Types
// =============================================================================

export interface ContextPillProps {
  /** Callback when the pill is clicked */
  onClick: () => void;
  /** Whether the pill is disabled */
  disabled?: boolean;
  /** Additional CSS classes */
  className?: string;
}

// =============================================================================
// Component
// =============================================================================

/**
 * Pill-shaped button with an @ icon and "Add context" label.
 * Designed to sit inside the SearchInput bottom toolbar.
 */
export function ContextPill({ onClick, disabled, className }: Readonly<ContextPillProps>) {
  return (
    <Button
      type='button'
      variant='ghost'
      size='sm'
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'border-border text-muted-foreground hover:text-foreground hover:border-foreground/20 gap-1 rounded-full border px-2.5 py-2 text-xs font-normal',
        className
      )}
    >
      <AtSign className='h-3.5 w-3.5' aria-hidden='true' />
      Add context
    </Button>
  );
}
