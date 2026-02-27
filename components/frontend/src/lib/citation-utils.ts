/**
 * Utilities for parsing and rendering [cite:N-start:end] annotation markers
 * produced by the aggregator's _annotate_cite_positions() backend method.
 *
 * Marker format: [cite:N-start:end]
 *   N     — source index (matches source_index_map keys, 1-based)
 *   start — char start of the cited sentence in clean (marker-free) text
 *   end   — char end of the cited sentence in clean (marker-free) text
 *
 * Multiple sources in one sentence: [cite:N,M-start:end]
 */

/** A single citation span: a sentence attributed to one or more sources. */
export interface CitationSpan {
  /** Source indices (match source_index_map keys) */
  indices: number[];
  /** Start char position in clean text (inclusive) */
  start: number;
  /** End char position in clean text (exclusive) */
  end: number;
}

// Matches [cite:N-start:end] and [cite:N,M-start:end]
const ANNOTATED_CITE_PATTERN = /\[cite:([\d,]+)-(\d+):(\d+)\]/g;
// Matches raw [cite:N] emitted during streaming (no position info)
const RAW_CITE_PATTERN = /\[cite:([\d,]+)\]/g;

/**
 * Strip all citation markers from text, returning clean prose.
 * Handles both raw [cite:N] (from streaming) and annotated [cite:N-start:end].
 */
export function stripCitations(text: string): string {
  return text
    .replaceAll(new RegExp(ANNOTATED_CITE_PATTERN.source, 'g'), '')
    .replaceAll(new RegExp(RAW_CITE_PATTERN.source, 'g'), '')
    .replaceAll(/ {2,}/g, ' ');
}

/**
 * Parse annotated citation markers from backend-annotated response text.
 *
 * Returns:
 *   cleanText — text with all [cite:…] markers removed
 *   spans     — citation spans with source indices and char positions
 */
export function parseCitations(annotatedText: string): {
  cleanText: string;
  spans: CitationSpan[];
} {
  const spans: CitationSpan[] = [];
  const re = new RegExp(ANNOTATED_CITE_PATTERN.source, 'g');
  let m: RegExpExecArray | null;

  while ((m = re.exec(annotatedText)) !== null) {
    const indicesRaw = m[1] ?? '';
    const startRaw = m[2] ?? '0';
    const endRaw = m[3] ?? '0';
    spans.push({
      indices: indicesRaw.split(',').map(Number),
      start: Number.parseInt(startRaw, 10),
      end: Number.parseInt(endRaw, 10)
    });
  }

  const cleanText = stripCitations(annotatedText);
  return { cleanText, spans };
}

/**
 * Convert annotated response text into markdown enriched with inline HTML
 * so cited sentences can be visually highlighted.
 *
 * Each cited span becomes:
 *   <mark class="cite-highlight" data-cite="N">…sentence…</mark>
 *   <sup class="cite-badge">N</sup>
 *
 * The output is intended for react-markdown with rehype-raw, which processes
 * the raw HTML elements while leaving surrounding markdown intact.
 *
 * Spans are injected right-to-left so earlier character positions stay valid
 * during string manipulation.
 */
export function buildCitedMarkdown(annotatedText: string): string {
  const { cleanText, spans } = parseCitations(annotatedText);
  if (spans.length === 0) return cleanText;

  // Deduplicate: merge spans with the same start/end range
  const byRange = new Map<string, CitationSpan>();
  for (const span of spans) {
    const key = `${span.start}:${span.end}`;
    const existing = byRange.get(key);
    if (existing) {
      existing.indices = [...new Set([...existing.indices, ...span.indices])];
    } else {
      byRange.set(key, { ...span });
    }
  }

  const sorted = [...byRange.values()].toSorted((a, b) => a.start - b.start);

  // Inject right-to-left to preserve char positions
  let result = cleanText;
  for (let index = sorted.length - 1; index >= 0; index--) {
    const span = sorted[index];
    if (!span) continue;
    const { start, end, indices } = span;
    const spanned = result.slice(start, end);
    const badges = indices.map((n: number) => `<sup class="cite-badge">${n}</sup>`).join('');
    const html = `<mark class="cite-highlight" data-cite="${indices.join(',')}">${spanned}</mark>${badges}`;
    result = result.slice(0, start) + html + result.slice(end);
  }

  return result;
}
