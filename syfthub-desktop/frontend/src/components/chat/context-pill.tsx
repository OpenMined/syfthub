import { AtSign } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface ContextPillProps {
  onClick: () => void;
  disabled?: boolean;
  className?: string;
}

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
