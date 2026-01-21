import React, { memo, Suspense, useCallback, useEffect, useMemo, useState } from 'react';

import Check from 'lucide-react/dist/esm/icons/check';
import Copy from 'lucide-react/dist/esm/icons/copy';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { cn } from '@/lib/utils';

// Lazy load react-syntax-highlighter to reduce initial bundle size (~300KB)
const SyntaxHighlighter = React.lazy(() => import('react-syntax-highlighter/dist/esm/prism-light'));

// Lazy load the style
const loadStyle = () =>
  import('react-syntax-highlighter/dist/esm/styles/prism/one-dark').then(
    (module_) => module_.default
  );

// Module-level style cache to avoid reloading
let cachedStyle: Record<string, React.CSSProperties> | null = null;

interface MarkdownMessageProps {
  content: string;
  className?: string;
}

// Code block component with syntax highlighting and copy button
const CodeBlock = memo(function CodeBlock({
  language,
  code
}: Readonly<{
  language: string | undefined;
  code: string;
}>) {
  const [copied, setCopied] = useState(false);
  const [style, setStyle] = useState<Record<string, React.CSSProperties> | null>(cachedStyle);

  // Load style on mount using lazy initialization with caching
  useEffect(() => {
    if (cachedStyle) {
      setStyle(cachedStyle);
      return;
    }

    let mounted = true;
    void loadStyle().then((loadedStyle) => {
      cachedStyle = loadedStyle;
      if (mounted) setStyle(loadedStyle);
    });
    return () => {
      mounted = false;
    };
  }, []);

  const copyToClipboard = useCallback(() => {
    void navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => {
      setCopied(false);
    }, 2000);
  }, [code]);

  // Custom style modifications for better appearance - memoized to prevent recreation
  const customStyle = useMemo(() => {
    if (!style) return {};
    return {
      ...style,
      'pre[class*="language-"]': {
        ...(style['pre[class*="language-"]'] as React.CSSProperties | undefined),
        background: 'transparent',
        margin: 0,
        padding: 0,
        fontSize: '13px',
        lineHeight: '1.5'
      },
      'code[class*="language-"]': {
        ...(style['code[class*="language-"]'] as React.CSSProperties | undefined),
        background: 'transparent',
        fontSize: '13px',
        lineHeight: '1.5'
      }
    };
  }, [style]);

  return (
    <div className='group relative my-3 overflow-hidden rounded-lg border border-[#3a3847] bg-[#1e1d2a]'>
      {/* Header with language and copy button */}
      <div className='flex items-center justify-between border-b border-[#3a3847] bg-[#16151f] px-3 py-1.5'>
        <span className='font-mono text-[11px] text-[#8b8a91]'>{language ?? 'text'}</span>
        <button
          onClick={copyToClipboard}
          className='flex items-center gap-1.5 rounded px-2 py-1 text-[11px] text-[#8b8a91] transition-colors hover:bg-white/10 hover:text-white'
        >
          {copied ? (
            <>
              <Check className='h-3 w-3' />
              <span>Copied!</span>
            </>
          ) : (
            <>
              <Copy className='h-3 w-3' />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      {/* Code content */}
      <div className='overflow-x-auto p-3'>
        <Suspense fallback={<pre className='font-mono text-[13px] text-gray-300'>{code}</pre>}>
          {style ? (
            <SyntaxHighlighter
              language={language ?? 'text'}
              style={customStyle}
              customStyle={{
                background: 'transparent',
                padding: 0,
                margin: 0
              }}
              codeTagProps={{
                style: {
                  fontSize: '13px',
                  lineHeight: '1.5'
                }
              }}
            >
              {code}
            </SyntaxHighlighter>
          ) : (
            <pre className='font-mono text-[13px] text-gray-300'>{code}</pre>
          )}
        </Suspense>
      </div>
    </div>
  );
});

// Memoized MarkdownMessage component to prevent re-renders when content hasn't changed
export const MarkdownMessage = memo(function MarkdownMessage({
  content,
  className
}: Readonly<MarkdownMessageProps>) {
  return (
    <div className={cn('markdown-message font-inter text-[15px] leading-relaxed', className)}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Headings
          h1: ({ children }) => (
            <h1 className='mt-5 mb-3 text-xl font-semibold text-[#272532] first:mt-0'>
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className='mt-4 mb-2 text-lg font-semibold text-[#272532] first:mt-0'>
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className='mt-3 mb-2 text-base font-semibold text-[#272532] first:mt-0'>
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className='mt-3 mb-1.5 text-sm font-semibold text-[#272532] first:mt-0'>
              {children}
            </h4>
          ),

          // Paragraphs
          p: ({ children }) => <p className='mb-3 last:mb-0'>{children}</p>,

          // Lists
          ul: ({ children }) => <ul className='mb-3 list-disc space-y-1 pl-5'>{children}</ul>,
          ol: ({ children }) => <ol className='mb-3 list-decimal space-y-1 pl-5'>{children}</ol>,
          li: ({ children }) => <li className='text-[#272532]'>{children}</li>,

          // Code - handle both inline and block
          code: ({ className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className ?? '');
            // Extract text content from children (typically a string or array for code elements)
            const getTextContent = (node: React.ReactNode): string => {
              if (typeof node === 'string') return node;
              if (typeof node === 'number') return node.toString();
              if (Array.isArray(node)) {
                return (node as React.ReactNode[])
                  .map((n: React.ReactNode) => getTextContent(n))
                  .join('');
              }
              return '';
            };
            const codeString = getTextContent(children).replace(/\n$/, '');

            // Check if this is a code block (has language class or is multiline)
            const isCodeBlock = Boolean(match) || codeString.includes('\n');

            if (isCodeBlock) {
              return <CodeBlock language={match?.[1]} code={codeString} />;
            }

            // Inline code
            return (
              <code
                className='rounded bg-[#e8e7ec] px-1.5 py-0.5 font-mono text-[13px] text-[#272532]'
                {...props}
              >
                {children}
              </code>
            );
          },

          // Pre - just pass through, code component handles formatting
          pre: ({ children }) => <>{children}</>,

          // Links
          a: ({ href, children }) => (
            <a
              href={href}
              className='text-[#6976ae] underline decoration-[#6976ae]/30 underline-offset-2 transition-colors hover:text-[#4d5a8c] hover:decoration-[#4d5a8c]/50'
              target='_blank'
              rel='noopener noreferrer'
            >
              {children}
            </a>
          ),

          // Blockquotes
          blockquote: ({ children }) => (
            <blockquote className='my-3 border-l-3 border-[#cfcdd6] bg-[#f1f0f4]/50 py-1 pl-4 text-[#5e5a72] italic'>
              {children}
            </blockquote>
          ),

          // Horizontal rule
          hr: () => <hr className='my-4 border-[#ecebef]' />,

          // Tables (GFM)
          table: ({ children }) => (
            <div className='my-3 overflow-x-auto rounded-lg border border-[#ecebef]'>
              <table className='min-w-full divide-y divide-[#ecebef]'>{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className='bg-[#f7f6f9]'>{children}</thead>,
          tbody: ({ children }) => (
            <tbody className='divide-y divide-[#ecebef] bg-white'>{children}</tbody>
          ),
          tr: ({ children }) => <tr>{children}</tr>,
          th: ({ children }) => (
            <th className='px-3 py-2 text-left text-xs font-semibold text-[#272532]'>{children}</th>
          ),
          td: ({ children }) => <td className='px-3 py-2 text-sm text-[#5e5a72]'>{children}</td>,

          // Strong and emphasis
          strong: ({ children }) => (
            <strong className='font-semibold text-[#272532]'>{children}</strong>
          ),
          em: ({ children }) => <em className='italic'>{children}</em>,

          // Delete (strikethrough from GFM)
          del: ({ children }) => <del className='text-[#8b8a91] line-through'>{children}</del>,

          // Images - lazy load for better performance (Web Interface Guidelines)
          img: ({ src, alt }) => (
            <img
              src={src}
              alt={alt ?? ''}
              loading='lazy'
              className='my-3 max-w-full rounded-lg border border-[#ecebef]'
            />
          )
        }}
      >
        {content}
      </Markdown>
    </div>
  );
});
