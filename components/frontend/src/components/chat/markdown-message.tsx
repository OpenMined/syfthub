import { memo } from 'react';

import { Markdown } from '@/components/prompt-kit/markdown';
import { cn } from '@/lib/utils';

interface MarkdownMessageProps {
  content: string;
  id?: string;
  className?: string;
}

export const MarkdownMessage = memo(function MarkdownMessage({
  content,
  id,
  className
}: Readonly<MarkdownMessageProps>) {
  return (
    <div className={cn('markdown-message font-inter text-[15px] leading-relaxed', className)}>
      <Markdown id={id}>{content}</Markdown>
    </div>
  );
});
