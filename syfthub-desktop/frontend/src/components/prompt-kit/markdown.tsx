import { memo, useId, useMemo } from 'react';

import type { Components } from 'react-markdown';

import { marked, type Token, type Tokens } from 'marked';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';

import { cn } from '@/lib/utils';

import { CodeBlock } from '@/components/tool-ui/code-block';

export type MarkdownProps = {
  children: string;
  id?: string;
  className?: string;
  components?: Partial<Components>;
  /** Allow raw HTML elements (e.g. <mark>, <sup>) embedded in markdown content. */
  allowRawHtml?: boolean;
};

type ParsedBlock =
  | { type: 'markdown'; content: string }
  | { type: 'code'; code: string; language: string };

function isCodeToken(token: Token): token is Tokens.Code {
  return token.type === 'code';
}

/**
 * Split markdown into blocks, extracting fenced code blocks as separate
 * entries so their code text (with indentation) never passes through
 * ReactMarkdown / remark-breaks which can collapse whitespace.
 */
function parseMarkdownIntoBlocks(markdown: string): ParsedBlock[] {
  const tokens = marked.lexer(markdown);
  return tokens.map((token) => {
    if (isCodeToken(token)) {
      return {
        type: 'code' as const,
        code: token.text,
        language: token.lang || 'plaintext',
      };
    }
    return { type: 'markdown' as const, content: token.raw };
  });
}

const INITIAL_COMPONENTS: Partial<Components> = {
  code: function CodeComponent({ className, children, ...props }) {
    return (
      <span
        className={cn('bg-primary-foreground rounded-sm px-1 font-mono text-sm', className)}
        {...props}
      >
        {children}
      </span>
    );
  },
};

const MemoizedMarkdownBlock = memo(
  function MarkdownBlock({
    content,
    components = INITIAL_COMPONENTS,
    allowRawHtml = false
  }: {
    content: string;
    components?: Partial<Components>;
    allowRawHtml?: boolean;
  }) {
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkBreaks]}
        rehypePlugins={allowRawHtml ? [rehypeRaw] : []}
        components={components}
      >
        {content}
      </ReactMarkdown>
    );
  },
  function propsAreEqual(prevProps, nextProps) {
    return (
      prevProps.content === nextProps.content && prevProps.allowRawHtml === nextProps.allowRawHtml
    );
  }
);

MemoizedMarkdownBlock.displayName = 'MemoizedMarkdownBlock';

const MemoizedCodeBlock = memo(
  function MemoCodeBlock({ code, language }: { code: string; language: string }) {
    if (language === 'plaintext') {
      return (
        <pre className='bg-card border-border overflow-x-auto rounded-lg border p-4 text-[13px]'>
          <code>{code}</code>
        </pre>
      );
    }
    return <CodeBlock id="" code={code} language={language} lineNumbers="hidden" />;
  },
  (prev, next) => prev.code === next.code && prev.language === next.language
);

MemoizedCodeBlock.displayName = 'MemoizedCodeBlock';

function MarkdownComponent({
  children,
  id,
  className,
  components = INITIAL_COMPONENTS,
  allowRawHtml = false
}: Readonly<MarkdownProps>) {
  const generatedId = useId();
  const blockId = id ?? generatedId;
  const blocks = useMemo(() => parseMarkdownIntoBlocks(children), [children]);

  return (
    <div className={className}>
      {blocks.map((block, index) => {
        if (block.type === 'code') {
          return (
            <MemoizedCodeBlock
              key={`${blockId}-block-${index}`}
              code={block.code}
              language={block.language}
            />
          );
        }
        return (
          <MemoizedMarkdownBlock
            key={`${blockId}-block-${index}`}
            content={block.content}
            components={components}
            allowRawHtml={allowRawHtml}
          />
        );
      })}
    </div>
  );
}

const Markdown = memo(MarkdownComponent);
Markdown.displayName = 'Markdown';

export { Markdown };
