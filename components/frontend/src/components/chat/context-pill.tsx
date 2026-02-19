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
        'text-muted-foreground hover:text-foreground h-9 gap-1 rounded-full px-3 text-sm font-normal',
        className
      )}
    >
      <AtSign className='h-4 w-4' aria-hidden='true' />
      Add context
    </Button>
  );
}
