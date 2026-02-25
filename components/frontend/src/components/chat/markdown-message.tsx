import { memo, useMemo } from 'react';

import { Markdown } from '@/components/prompt-kit/markdown';
import { buildCitedMarkdown, stripCitations } from '@/lib/citation-utils';
import { cn } from '@/lib/utils';

interface MarkdownMessageProps {
  content: string;
  /**
   * Position-annotated response from the aggregator's done event.
   * When present, cited sentences are highlighted with inline badges.
   * Format: text with [cite:N-start:end] markers produced by _annotate_cite_positions().
   */
  annotatedContent?: string;
  id?: string;
  className?: string;
}

export const MarkdownMessage = memo(function MarkdownMessage({
  content,
  annotatedContent,
  id,
  className
}: Readonly<MarkdownMessageProps>) {
  const { renderedContent, hasCitations } = useMemo(() => {
    if (annotatedContent) {
      // Final response: convert [cite:N-start:end] markers to <mark>/<sup> HTML
      return { renderedContent: buildCitedMarkdown(annotatedContent), hasCitations: true };
    }
    // Streaming: strip raw [cite:N] markers — no position info yet
    return { renderedContent: stripCitations(content), hasCitations: false };
  }, [content, annotatedContent]);

  return (
    <div className={cn('markdown-message font-inter text-[15px] leading-relaxed', className)}>
      <Markdown id={id} allowRawHtml={hasCitations}>
        {renderedContent}
      </Markdown>
    </div>
  );
});
