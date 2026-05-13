import type { buttonVariants } from '@/components/ui/button';

import { type VariantProps } from 'class-variance-authority';
import { ChevronDown } from 'lucide-react';
import { useStickToBottomContext } from 'use-stick-to-bottom';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export type ScrollButtonProps = {
  className?: string;
  variant?: VariantProps<typeof buttonVariants>['variant'];
  size?: VariantProps<typeof buttonVariants>['size'];
} & React.ButtonHTMLAttributes<HTMLButtonElement>;

function ScrollButton({
  className,
  variant = 'outline',
  size = 'sm',
  ...props
}: ScrollButtonProps) {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();

  return (
    <Button
      variant={variant}
      size={size}
      aria-label='Scroll to latest'
      className={cn(
        'bg-card text-foreground hover:bg-muted h-9 w-9 rounded-lg border shadow-md transition-all duration-150 ease-out',
        isAtBottom
          ? 'pointer-events-none translate-y-4 scale-95 opacity-0'
          : 'translate-y-0 scale-100 opacity-100',
        className
      )}
      onClick={() => scrollToBottom()}
      {...props}
    >
      <ChevronDown className='h-4 w-4' aria-hidden='true' />
    </Button>
  );
}

export { ScrollButton };
