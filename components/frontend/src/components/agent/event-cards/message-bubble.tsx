/**
 * Agent/user message with markdown rendering.
 */

interface MessageBubbleProps {
  readonly content: string;
  readonly isComplete: boolean;
  readonly role: 'assistant' | 'user';
}

export function MessageBubble({ content, isComplete, role }: MessageBubbleProps) {
  const isAssistant = role === 'assistant';

  return (
    <div
      className={`rounded-lg p-3 ${
        isAssistant ? 'bg-muted/50 border' : 'bg-primary/10 border-primary/20 ml-8 border'
      }`}
    >
      <div className='flex items-start gap-2'>
        <span className='text-muted-foreground text-xs font-medium uppercase'>
          {isAssistant ? 'Agent' : 'You'}
        </span>
        {!isComplete && <div className='mt-1 h-2 w-2 animate-pulse rounded-full bg-blue-500' />}
      </div>
      <div className='mt-1 text-sm whitespace-pre-wrap'>{content}</div>
    </div>
  );
}
