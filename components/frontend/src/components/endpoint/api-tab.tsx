import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { EndpointType } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';
import Copy from 'lucide-react/dist/esm/icons/copy';
import { Link } from 'react-router-dom';

import { CodeBlock, CodeBlockCode, CodeBlockGroup } from '@/components/prompt-kit/code-block';
import { Button } from '@/components/ui/button';

interface ApiTabProperties {
  endpointPath: string;
  endpointType: EndpointType;
}

const PLACEHOLDER_MODEL = 'owner/your-model-slug';
const FILENAME = 'query.py';

function buildSnippet(path: string, dataSourceOnly: boolean): string {
  const model = dataSourceOnly ? `"${PLACEHOLDER_MODEL}"` : `"${path}"`;
  const dataSources = dataSourceOnly ? `\n    data_sources=["${path}"],` : '';
  const origin = globalThis.location.origin;
  return `from syfthub_sdk import SyftHubClient

client = SyftHubClient(
    base_url="${origin}",
    api_token="syft_pat_...",
)

response = client.chat.complete(
    prompt="Hello, world!",
    model=${model},${dataSources}
)
print(response.response)

client.close()
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

export function ApiTab({ endpointPath, endpointType }: Readonly<ApiTabProperties>) {
  const dataSourceOnly = endpointType === 'data_source';

  const code = useMemo(
    () => buildSnippet(endpointPath, dataSourceOnly),
    [endpointPath, dataSourceOnly]
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
          {dataSourceOnly ? (
            <>
              . Because this endpoint is a data source, pair it with any model endpoint in the{' '}
              <code className='bg-muted text-foreground rounded px-1.5 py-0.5 font-mono text-xs'>
                model
              </code>{' '}
              field.
            </>
          ) : (
            '.'
          )}
        </p>
      </header>

      <SnippetCard filename={FILENAME} code={code} language='python' />
    </section>
  );
}
