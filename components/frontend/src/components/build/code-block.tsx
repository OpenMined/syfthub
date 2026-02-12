import React, { memo, Suspense, useCallback, useState } from 'react';

import Check from 'lucide-react/dist/esm/icons/check';
import Copy from 'lucide-react/dist/esm/icons/copy';
import { PrismLight as SyntaxHighlighterBase } from 'react-syntax-highlighter';
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';

import { Button } from '@/components/ui/button';

// Register languages for syntax highlighting (prism-light requires explicit registration)
SyntaxHighlighterBase.registerLanguage('bash', bash);
SyntaxHighlighterBase.registerLanguage('python', python);
SyntaxHighlighterBase.registerLanguage('typescript', typescript);
SyntaxHighlighterBase.registerLanguage('json', json);

// Wrap in lazy for code-splitting (the component itself is small, languages are registered above)
const SyntaxHighlighter = React.lazy(() => Promise.resolve({ default: SyntaxHighlighterBase }));

// Lazy load the style - will be loaded alongside SyntaxHighlighter
const loadStyle = () =>
  import('react-syntax-highlighter/dist/esm/styles/prism/vsc-dark-plus').then(
    (module_) => module_.default
  );

export interface CodeBlockProps {
  code: string;
  language: string;
}

// Memoized CodeBlock component with lazy-loaded syntax highlighter
export const CodeBlock = memo(function CodeBlock({ code, language }: Readonly<CodeBlockProps>) {
  const [copied, setCopied] = useState(false);
  const [style, setStyle] = useState<Record<string, React.CSSProperties> | null>(null);

  // Load style on mount using lazy initialization
  React.useEffect(() => {
    let mounted = true;
    void loadStyle().then((loadedStyle) => {
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

  // Custom style to match the existing dark theme
  const customStyle = React.useMemo(() => {
    if (!style) return {};
    return {
      ...style,
      'pre[class*="language-"]': {
        ...(style['pre[class*="language-"]'] as React.CSSProperties | undefined),
        background: 'transparent',
        margin: 0,
        padding: 0,
        fontSize: '14px',
        lineHeight: '1.5'
      },
      'code[class*="language-"]': {
        ...(style['code[class*="language-"]'] as React.CSSProperties | undefined),
        background: 'transparent',
        fontSize: '14px',
        lineHeight: '1.5'
      }
    };
  }, [style]);

  return (
    <div className='group border-border relative overflow-hidden rounded-xl border bg-[#1a1923]'>
      <div className='absolute top-2 right-2 opacity-0 transition-opacity group-hover:opacity-100'>
        <Button
          variant='ghost'
          size='icon'
          className='text-muted-foreground h-8 w-8 hover:bg-white/10 hover:text-white'
          onClick={copyToClipboard}
        >
          {copied ? <Check className='h-4 w-4' /> : <Copy className='h-4 w-4' />}
        </Button>
      </div>
      <div className='flex items-center justify-between border-b border-white/5 bg-[#131219] px-4 py-2'>
        <span className='text-muted-foreground font-mono text-xs'>{language}</span>
      </div>
      <div className='overflow-x-auto p-4'>
        <Suspense fallback={<pre className='text-muted-foreground font-mono text-sm'>{code}</pre>}>
          {style ? (
            <SyntaxHighlighter
              language={language}
              style={customStyle}
              customStyle={{
                background: 'transparent',
                padding: 0,
                margin: 0
              }}
              codeTagProps={{
                style: {
                  fontSize: '14px',
                  lineHeight: '1.5'
                }
              }}
            >
              {code}
            </SyntaxHighlighter>
          ) : (
            <pre className='text-muted-foreground font-mono text-sm'>{code}</pre>
          )}
        </Suspense>
      </div>
    </div>
  );
});
