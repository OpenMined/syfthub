import { useEffect, useState } from 'react';

import type { DoneEvent } from '@/lib/sdk-client';

import { useSearchParams } from 'react-router-dom';

import { useAuth } from '@/context/auth-context';
import { getErrorMessage } from '@/hooks/use-chat-workflow';
import { AggregatorError, syftClient } from '@/lib/sdk-client';

const DEFAULT_MODEL =
  (import.meta.env.VITE_DEFAULT_MODEL as string | undefined) ?? 'testuser/llm-proxy';

// ─── URL Parsing ─────────────────────────────────────────────────────────────

type ParseSuccess = { dataSources: string[]; prompt: string };
type ParseError = { error: string };
type ParseResult = ParseSuccess | ParseError;

/**
 * Parse the `q` URL parameter into structured data.
 *
 * Expected format: `owner/slug1|owner/slug2!user prompt`
 * - Pipe-delimited endpoint slugs (owner/slug) before `!`
 * - User prompt after `!`
 * - Empty slug section is valid (model-only query)
 *
 * @param q - Raw `q` parameter value from URLSearchParams, or null if absent
 * @returns ParseSuccess on valid input, ParseError with description on failure
 */
export function parseQueryParam(q: string | null): ParseResult {
  if (!q) {
    return {
      error: "Missing 'q' parameter. Expected format: owner/slug1|owner/slug2!your+query"
    };
  }

  const bangIndex = q.indexOf('!');
  if (bangIndex === -1) {
    return {
      error:
        "Invalid query format: missing '!' separator. Expected: owner/slug1|owner/slug2!your+query"
    };
  }

  const prompt = q.slice(bangIndex + 1).trim();
  if (!prompt) {
    return { error: "Empty prompt: add your question after the '!'." };
  }

  const slugPart = q.slice(0, bangIndex);
  const dataSources = slugPart
    ? slugPart
        .split('|')
        .map((s) => s.trim())
        .filter(Boolean)
    : [];

  for (const slug of dataSources) {
    if (!slug.includes('/')) {
      return {
        error: `Invalid endpoint format '${slug}'. Expected owner/slug (e.g. openmined/wiki).`
      };
    }
  }

  return { dataSources, prompt };
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface QueryResult {
  query: string;
  model: string;
  data_sources: string[];
  answer: string | null;
  sources: DoneEvent['sources'];
  error: string | null;
}

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * QueryPage — URL-based JSON query interface.
 *
 * Accepts a `q` URL parameter in the format:
 *   /q?q=owner/slug1|owner/slug2!user+prompt
 *
 * Executes the full RAG chat workflow client-side (same privacy model as /chat:
 * backend only issues satellite tokens, never sees the prompt) and renders the
 * complete response as formatted JSON.
 *
 * Privacy: the user's prompt is sent directly from the browser to the aggregator.
 * The hub backend only receives endpoint owner usernames (for token issuance).
 */
export default function QueryPage() {
  const [searchParams] = useSearchParams();
  const { user, isInitializing } = useAuth();
  const isGuest = !user;
  const [result, setResult] = useState<QueryResult | null>(null);
  const [statusMessage, setStatusMessage] = useState('Preparing request...');
  const q = searchParams.get('q');

  useEffect(() => {
    if (isInitializing) return;

    const parsed = parseQueryParam(q);

    if ('error' in parsed) {
      setResult({
        query: q ?? '',
        model: DEFAULT_MODEL,
        data_sources: [],
        answer: null,
        sources: {},
        error: parsed.error
      });
      return;
    }

    const { dataSources, prompt } = parsed;
    const controller = new AbortController();

    let answer = '';
    let finalSources: DoneEvent['sources'] = {};

    async function run() {
      try {
        setStatusMessage('Preparing request...');

        const stream = syftClient.chat.stream({
          model: DEFAULT_MODEL,
          dataSources,
          prompt,
          guestMode: isGuest,
          signal: controller.signal
        });

        for await (const event of stream) {
          if (controller.signal.aborted) return;

          switch (event.type) {
            case 'retrieval_start': {
              setStatusMessage(
                `Searching ${event.sourceCount} data source${event.sourceCount === 1 ? '' : 's'}...`
              );
              break;
            }
            case 'source_complete': {
              setStatusMessage(
                `Retrieved ${event.documentsRetrieved} document${event.documentsRetrieved === 1 ? '' : 's'} from ${event.path}`
              );
              break;
            }
            case 'reranking_start': {
              setStatusMessage('Reranking results...');
              break;
            }
            case 'generation_start': {
              setStatusMessage('Generating answer...');
              break;
            }
            case 'token': {
              answer += event.content;
              break;
            }
            case 'done': {
              // Prefer the clean cite-tag-stripped response if attribution ran
              if (event.response) {
                answer = event.response;
              }
              finalSources = event.sources ?? {};
              break;
            }
            case 'error': {
              throw new AggregatorError(event.message);
            }
          }
        }

        setResult({
          query: prompt,
          model: DEFAULT_MODEL,
          data_sources: dataSources,
          answer,
          sources: finalSources,
          error: null
        });
      } catch (error) {
        if (controller.signal.aborted) return;

        setResult({
          query: prompt,
          model: DEFAULT_MODEL,
          data_sources: dataSources,
          answer: null,
          sources: {},
          error: getErrorMessage(error)
        });
      }
    }

    void run();

    return () => {
      controller.abort();
    };
  }, [q, isGuest, isInitializing]);

  if (!result) {
    return (
      <div className='bg-background text-foreground flex min-h-screen items-center justify-center p-8'>
        <div className='space-y-3 text-center'>
          <div className='text-muted-foreground font-mono text-sm'>{statusMessage}</div>
          <div className='bg-primary mx-auto h-2 w-2 animate-pulse rounded-full' />
        </div>
      </div>
    );
  }

  return (
    <div className='bg-background text-foreground min-h-screen p-4'>
      <pre className='font-mono text-sm break-words whitespace-pre-wrap'>
        {JSON.stringify(result, null, 2)}
      </pre>
    </div>
  );
}
