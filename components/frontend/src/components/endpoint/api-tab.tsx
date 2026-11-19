import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { EndpointType, FilterSchema } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';
import Copy from 'lucide-react/dist/esm/icons/copy';
import { Link } from 'react-router-dom';

import { CodeBlock, CodeBlockCode, CodeBlockGroup } from '@/components/prompt-kit/code-block';
import { Button } from '@/components/ui/button';

interface ApiTabProperties {
  endpointPath: string;
  endpointType: EndpointType;
  filters?: FilterSchema | null;
}

const FILENAME = 'search.py';

const SUGAR: Record<string, string> = {
  eq: '==',
  ne: '!=',
  gt: '>',
  gte: '>=',
  lt: '<',
  lte: '<='
};
const METHOD: Record<string, string> = {
  in: 'in_',
  nin: 'not_in',
  contains_any: 'contains_any',
  contains_all: 'contains_all'
};
const SAMPLE: Record<string, string> = {
  string: '"value"',
  number: '0',
  boolean: 'True',
  datetime: '"2026-01-01"'
};

/** `F("field") >= "2026-01-01"` for the first filterable field, or null when there is none. */
export function sampleFilter(filters?: FilterSchema | null): string | null {
  const first = filters ? Object.entries(filters.fields)[0] : undefined;
  const op = first?.[1].ops[0];
  if (!first || !op) return null;
  const [name, spec] = first;
  const sample = SAMPLE[spec.type.replace('[]', '')] ?? '"value"';
  const sugar = SUGAR[op];
  if (sugar) return `F("${name}") ${sugar} ${sample}`;
  const method = METHOD[op];
  if (method) return `F("${name}").${method}([${sample}])`;
  return `F("${name}").op("${op}", ${sample})`;
}

export function buildSnippet(
  path: string,
  dataSourceOnly: boolean,
  filters?: FilterSchema | null
): string {
  const origin = globalThis.location.origin;
  const filter = sampleFilter(filters);
  const read = dataSourceOnly
    ? `    for path, doc in results.documents:  # scored chunks, best first
        print(path, doc.score, doc.content[:80])`
    : `    print(results.answers["${path}"])  # what the model returned`;
  const compose = filter
    ? `    source = hub.sources.get("${path}")
    plan = hub.search("Hello, world!", [source.where(${filter})])  # narrow by metadata`
    : `    plan = hub.search("Hello, world!", ["${path}"])`;
  return `# pip install --pre syfthub-sdk
import syfthub${filter ? '\nfrom syfthub import F' : ''}

with syfthub.Hub("${origin}", token="syft_pat_...") as hub:
${compose}
    pre = plan.preflight()  # nothing sent yet
    print(pre.ready, pre.estimate)  # can it run, and what it will cost
    results = plan.execute()
${read}
`;
}

interface CopyButtonProperties {
  text: string;
  label: string;
}

function CopyButton({ text, label }: Readonly<CopyButtonProperties>) {
  const [copied, setCopied] = useState(false);
  const timerReference = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timerReference.current) clearTimeout(timerReference.current);
    },
    []
  );

  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(text);
    setCopied(true);
    if (timerReference.current) clearTimeout(timerReference.current);
    timerReference.current = setTimeout(() => {
      setCopied(false);
    }, 2000);
  }, [text]);

  return (
    <Button
      type='button'
      variant='ghost'
      size='sm'
      onClick={handleCopy}
      aria-label={copied ? `${label} copied` : `Copy ${label}`}
      className='text-muted-foreground hover:text-foreground h-8 gap-1.5 px-2 text-xs'
    >
      {copied ? (
        <>
          <Check className='h-3.5 w-3.5 text-green-600' aria-hidden='true' />
          Copied
        </>
      ) : (
        <>
          <Copy className='h-3.5 w-3.5' aria-hidden='true' />
          Copy
        </>
      )}
    </Button>
  );
}

interface SnippetCardProperties {
  filename: string;
  code: string;
  language: string;
}

function SnippetCard({ filename, code, language }: Readonly<SnippetCardProperties>) {
  return (
    <CodeBlock>
      <CodeBlockGroup className='border-border bg-muted/40 border-b px-4 py-2'>
        <span className='font-inter text-muted-foreground text-xs font-medium'>{filename}</span>
        <CopyButton text={code} label={filename} />
      </CodeBlockGroup>
      <CodeBlockCode code={code} language={language} />
    </CodeBlock>
  );
}

export function ApiTab({ endpointPath, endpointType, filters }: Readonly<ApiTabProperties>) {
  const dataSourceOnly = endpointType === 'data_source';

  const code = useMemo(
    () => buildSnippet(endpointPath, dataSourceOnly, filters),
    [endpointPath, dataSourceOnly, filters]
  );

  return (
    <section className='space-y-6'>
      <header className='space-y-1'>
        <h2 className='font-rubik text-foreground text-xl font-medium'>Use this endpoint</h2>
        <p className='font-inter text-muted-foreground text-sm'>
          Copy and paste a snippet to query{' '}
          <code className='bg-muted text-foreground rounded px-1.5 py-0.5 font-mono text-xs'>
            {endpointPath}
          </code>{' '}
          programmatically with the Python SDK. Generate a personal access token from your{' '}
          <Link to='/profile?tab=tokens' className='text-secondary hover:underline'>
            profile settings
          </Link>{' '}
          and replace{' '}
          <code className='bg-muted text-foreground rounded px-1.5 py-0.5 font-mono text-xs'>
            syft_pat_...
          </code>
          . Pre-flight shows what the query costs and needs before anything is sent.
        </p>
      </header>

      <SnippetCard filename={FILENAME} code={code} language='python' />
    </section>
  );
}
