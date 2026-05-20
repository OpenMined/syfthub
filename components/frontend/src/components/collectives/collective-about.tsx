import { useMemo } from 'react';

import type { Components } from 'react-markdown';

import ExternalLink from 'lucide-react/dist/esm/icons/external-link';

import { Markdown } from '@/components/prompt-kit/markdown';
import { Card } from '@/components/ui/card';

interface CollectiveAboutProps {
  /** Long-form markdown content from `Collective.about`. */
  about: string;
}

/**
 * The "About" card on the collective detail page — renders the collective's
 * long-form markdown `about` field. Mirrors the user-profile About section.
 */
export function CollectiveAbout({ about }: Readonly<CollectiveAboutProps>) {
  const components = useMemo(
    (): Components => ({
      h1: ({ children }) => (
        <h1 className='font-rubik text-foreground mt-4 mb-3 text-xl font-medium'>{children}</h1>
      ),
      h2: ({ children }) => (
        <h2 className='font-rubik text-foreground mt-4 mb-2 text-lg font-medium'>{children}</h2>
      ),
      h3: ({ children }) => (
        <h3 className='font-rubik text-foreground mt-3 mb-2 text-base font-medium'>{children}</h3>
      ),
      p: ({ children }) => <p className='font-inter text-muted-foreground mb-3'>{children}</p>,
      ul: ({ children }) => <ul className='mb-3 list-disc space-y-1 pl-5'>{children}</ul>,
      ol: ({ children }) => <ol className='mb-3 list-decimal space-y-1 pl-5'>{children}</ol>,
      li: ({ children }) => <li className='font-inter text-muted-foreground'>{children}</li>,
      a: ({ href, children }) => (
        <a
          href={href}
          className='text-secondary hover:text-foreground inline-flex items-center gap-0.5 hover:underline'
          target='_blank'
          rel='noopener noreferrer'
        >
          {children}
          <ExternalLink className='ml-0.5 inline-block h-3 w-3 flex-shrink-0' aria-hidden='true' />
          <span className='sr-only'>(opens in new tab)</span>
        </a>
      ),
      code: ({ className, children }) => {
        const isInline = !className;
        return isInline ? (
          <code className='bg-muted text-foreground rounded px-1 py-0.5 font-mono text-xs'>
            {children}
          </code>
        ) : (
          <code className='block'>{children}</code>
        );
      },
      blockquote: ({ children }) => (
        <blockquote className='border-border text-muted-foreground my-3 border-l-4 pl-4 italic'>
          {children}
        </blockquote>
      )
    }),
    []
  );

  return (
    <Card
      aria-labelledby='collective-about-heading'
      className='border-border bg-card rounded-xl border p-6'
    >
      <h2 id='collective-about-heading' className='mb-4 text-lg font-semibold'>
        About
      </h2>
      <div className='prose prose-sm max-w-none'>
        <Markdown components={components}>{about}</Markdown>
      </div>
    </Card>
  );
}
