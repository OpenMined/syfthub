import { cn } from '@/lib/utils';

export type MessageProps = {
  children: React.ReactNode;
  className?: string;
} & React.HTMLProps<HTMLDivElement>;

const Message = ({ children, className, ...props }: MessageProps) => (
  <div className={cn('flex gap-3', className)} {...props}>
    {children}
  </div>
);

export type MessageContentProps = {
  children: React.ReactNode;
  className?: string;
} & React.HTMLProps<HTMLDivElement>;

const MessageContent = ({ children, className, ...props }: MessageContentProps) => (
  <div
    className={cn('text-foreground rounded-lg p-2 break-words whitespace-normal', className)}
    {...props}
  >
    {children}
  </div>
);

export { Message, MessageContent };
