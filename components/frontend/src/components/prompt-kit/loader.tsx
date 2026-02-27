import { cn } from '@/lib/utils';

type LoaderVariant =
  | 'circular'
  | 'classic'
  | 'pulse'
  | 'pulse-dot'
  | 'dots'
  | 'typing'
  | 'wave'
  | 'bars'
  | 'terminal'
  | 'text-blink'
  | 'text-shimmer'
  | 'loading-dots';

type LoaderSize = 'sm' | 'md' | 'lg';

export type LoaderProps = {
  variant?: LoaderVariant;
  size?: LoaderSize;
  text?: string;
  className?: string;
};

export function DotsLoader({
  className,
  size = 'md'
}: Readonly<{
  className?: string;
  size?: LoaderSize;
}>) {
  const dotSizes = {
    sm: 'h-1.5 w-1.5',
    md: 'h-2 w-2',
    lg: 'h-2.5 w-2.5'
  };

  const containerSizes = {
    sm: 'h-4',
    md: 'h-5',
    lg: 'h-6'
  };

  return (
    <div className={cn('flex items-center space-x-1', containerSizes[size], className)}>
      {Array.from({ length: 3 }).map((_, index) => (
        <div
          key={index}
          className={cn(
            'bg-primary animate-[bounce-dots_1.4s_ease-in-out_infinite] rounded-full',
            dotSizes[size]
          )}
          style={{ animationDelay: `${String(index * 160)}ms` }}
        />
      ))}
      <span className='sr-only'>Loading</span>
    </div>
  );
}

export function TypingLoader({
  className,
  size = 'md'
}: Readonly<{
  className?: string;
  size?: LoaderSize;
}>) {
  const dotSizes = {
    sm: 'h-1 w-1',
    md: 'h-1.5 w-1.5',
    lg: 'h-2 w-2'
  };

  const containerSizes = {
    sm: 'h-4',
    md: 'h-5',
    lg: 'h-6'
  };

  return (
    <div className={cn('flex items-center space-x-1', containerSizes[size], className)}>
      {Array.from({ length: 3 }).map((_, index) => (
        <div
          key={index}
          className={cn('bg-primary animate-[typing_1s_infinite] rounded-full', dotSizes[size])}
          style={{ animationDelay: `${String(index * 250)}ms` }}
        />
      ))}
      <span className='sr-only'>Loading</span>
    </div>
  );
}

export function CircularLoader({
  className,
  size = 'md'
}: Readonly<{
  className?: string;
  size?: LoaderSize;
}>) {
  const sizeClasses = { sm: 'size-4', md: 'size-5', lg: 'size-6' };

  return (
    <div
      className={cn(
        'border-primary animate-spin rounded-full border-2 border-t-transparent',
        sizeClasses[size],
        className
      )}
    >
      <span className='sr-only'>Loading</span>
    </div>
  );
}

function Loader({ variant = 'circular', size = 'md', className }: Readonly<LoaderProps>) {
  switch (variant) {
    case 'dots': {
      return <DotsLoader size={size} className={className} />;
    }
    case 'typing': {
      return <TypingLoader size={size} className={className} />;
    }
    default: {
      return <CircularLoader size={size} className={className} />;
    }
  }
}

export { Loader };
