import { cn } from '@/lib/utils';

interface ErrorBannerProps {
  message: string | null | undefined;
  className?: string;
}

export function ErrorBanner({ message, className }: ErrorBannerProps) {
  if (!message) return null;
  return (
    <div className={cn(
      "bg-destructive/10 border border-destructive/20 rounded-lg p-3 text-destructive text-sm",
      className
    )}>
      {message}
    </div>
  );
}
