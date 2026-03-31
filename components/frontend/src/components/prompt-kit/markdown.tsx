import { isValidElement, memo, useId, useMemo } from 'react';

import type { ReactNode } from 'react';
import type { Components } from 'react-markdown';

import { marked } from 'marked';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';

import { cn } from '@/lib/utils';

import { CodeBlock, CodeBlockCode } from './code-block';

export type MarkdownProps = {
  children: string;
  id?: string;
  className?: string;
  components?: Partial<Components>;
  /** Allow raw HTML elements (e.g. <mark>, <sup>) embedded in markdown content. */
  allowRawHtml?: boolean;
};

function parseMarkdownIntoBlocks(markdown: string): string[] {
  const tokens = marked.lexer(markdown);
  return tokens.map((token) => token.raw);
}

function extractLanguage(className?: string): string {
  if (!className) return 'plaintext';
  const match = /language-(\w+)/.exec(className);
  return match?.[1] ?? 'plaintext';
}

/** Recursively extract text from React children, converting <br> back to \n. */
function flattenChildren(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string') return node;
  if (typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map((n) => flattenChildren(n as ReactNode)).join('');
  if (isValidElement(node)) {
    if (node.type === 'br') return '\n';
    const props = node.props as Record<string, unknown>;
    if (props.children) return flattenChildren(props.children as ReactNode);
  }
  return '';
}

const INITIAL_COMPONENTS: Partial<Components> = {
  code: function CodeComponent({ className, children, ...props }) {
    const isInline =
      !props.node?.position?.start.line ||
      props.node?.position?.start.line === props.node?.position?.end.line;

    if (isInline) {
      return (
        <span
          className={cn('bg-primary-foreground rounded-sm px-1 font-mono text-sm', className)}
          {...props}
        >
          {children}
        </span>
      );
    }

    const language = extractLanguage(className);
    const code = flattenChildren(children);

    return (
      <CodeBlock className={className}>
        <CodeBlockCode code={code} language={language} />
      </CodeBlock>
    );
  },
  pre: function PreComponent({ children }) {
    return <>{children}</>;
  }
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
      {blocks.map((block, index) => (
        <MemoizedMarkdownBlock
          key={`${blockId}-block-${index}`}
          content={block}
          components={components}
          allowRawHtml={allowRawHtml}
        />
      ))}
    </div>
  );
}

const Markdown = memo(MarkdownComponent);
Markdown.displayName = 'Markdown';

export { Markdown };
