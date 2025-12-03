import { cn } from '@/lib/utils';

interface LoadingSpinnerProperties {
  size?: 'sm' | 'md' | 'lg';
  message?: string;
  className?: string;
  fullScreen?: boolean;
}

const sizeClasses = {
  sm: 'h-4 w-4 border',
  md: 'h-6 w-6 border-2',
  lg: 'h-8 w-8 border-2'
};

export function LoadingSpinner({
  size = 'md',
  message,
  className,
  fullScreen = false
}: Readonly<LoadingSpinnerProperties>) {
  const spinner = (
    <div className={cn('flex items-center gap-3', className)}>
      <div
        className={cn(
          'border-syft-primary animate-spin rounded-full border-t-transparent',
          sizeClasses[size]
        )}
      />
      {message && <span className='font-inter text-syft-primary'>{message}</span>}
    </div>
  );

  if (fullScreen) {
    return (
      <div className='bg-syft-background flex min-h-screen items-center justify-center'>
        {spinner}
      </div>
    );
  }

  return spinner;
}
