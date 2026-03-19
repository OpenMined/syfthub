import { useEffect, useState } from 'react';

import { useSearchParams } from 'react-router-dom';

const AGGREGATOR_BASE = '/aggregator/api/v1';

/**
 * QueryPage — URL-based query interface returning server-rendered HTML.
 *
 * Accepts a `q` URL parameter in the format:
 *   /q?q=owner/slug1|owner/slug2!user+prompt
 *
 * Delegates entirely to the aggregator's GET /api/v1/q endpoint,
 * which resolves endpoints, acquires tokens, runs the RAG pipeline,
 * and returns a self-contained HTML page.
 */
export default function QueryPage() {
  const [searchParams] = useSearchParams();
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const q = searchParams.get('q');

  useEffect(() => {
    if (!q) {
      setError("Missing 'q' parameter. Expected format: owner/slug1|owner/slug2!your+query");
      return;
    }

    const controller = new AbortController();

    fetch(`${AGGREGATOR_BASE}/q?q=${encodeURIComponent(q)}`, {
      signal: controller.signal
    })
      .then(async (resp) => {
        if (controller.signal.aborted) return;
        const text = await resp.text();
        if (resp.ok) {
          setHtml(text);
        } else {
          setError(`Aggregator error (${String(resp.status)}): ${text}`);
        }
      })
      .catch((error_: unknown) => {
        if (controller.signal.aborted) return;
        setError(error_ instanceof Error ? error_.message : String(error_));
      });

    return () => {
      controller.abort();
    };
  }, [q]);

  if (error) {
    return (
      <div className='bg-background text-foreground min-h-screen p-4'>
        <pre className='font-mono text-sm break-words whitespace-pre-wrap'>
          {JSON.stringify({ query: q ?? '', error }, null, 2)}
        </pre>
      </div>
    );
  }

  if (!html) {
    return (
      <div className='bg-background text-foreground flex min-h-screen flex-col items-center justify-center gap-3 p-8 text-center'>
        <div className='text-muted-foreground font-mono text-sm'>Querying...</div>
        <div className='bg-primary h-2 w-2 animate-pulse rounded-full' />
      </div>
    );
  }

  return (
    <iframe
      srcDoc={html}
      title='Query Result'
      className='h-screen w-full border-0'
      sandbox='allow-same-origin'
    />
  );
}
