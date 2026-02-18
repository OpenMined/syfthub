/**
 * Mention Utilities
 *
 * Utilities for parsing and managing @owner/slug mentions in text input.
 */
import type { ChatSource } from '@/lib/types';

// =============================================================================
// Types
// =============================================================================

export type MentionPhase = 'idle' | 'owner' | 'slug';

export interface MentionState {
  /** Current phase of mention parsing */
  phase: MentionPhase;
  /** Start position of the @ character in the text */
  startIndex: number;
  /** The owner being typed (after @, before /) */
  ownerText: string;
  /** The slug being typed (after /) */
  slugText: string;
  /** The full mention text including @ */
  fullText: string;
}

export interface OwnerInfo {
  /** Username of the owner */
  username: string;
  /** Number of endpoints owned */
  endpointCount: number;
}

// =============================================================================
// Parsing Functions
// =============================================================================

/** Scans backward from cursorPos to find the index of an '@' not preceded by whitespace. */
function findAtSignIndex(text: string, cursorPos: number): number {
  for (let index = cursorPos - 1; index >= 0; index--) {
    const char = text.charAt(index);
    if (/\s/.test(char)) break;
    if (char === '@') return index;
  }
  return -1;
}

/** Builds owner-phase state if mentionText is a valid owner mention, or returns null. */
function buildOwnerPhaseState(mentionText: string, atIndex: number): MentionState | null {
  const ownerText = mentionText.slice(1); // Remove @
  if (ownerText && !/^[a-zA-Z0-9_-]*$/.test(ownerText)) return null;
  return { phase: 'owner', startIndex: atIndex, ownerText, slugText: '', fullText: mentionText };
}

/** Builds slug-phase state if mentionText is a valid owner/slug mention, or returns null. */
function buildSlugPhaseState(
  mentionText: string,
  atIndex: number,
  slashIndex: number
): MentionState | null {
  const ownerText = mentionText.slice(1, slashIndex); // Between @ and /
  const slugText = mentionText.slice(slashIndex + 1); // After /
  if (ownerText && !/^[a-zA-Z0-9_-]+$/.test(ownerText)) return null;
  if (slugText && !/^[a-zA-Z0-9_-]*$/.test(slugText)) return null;
  return { phase: 'slug', startIndex: atIndex, ownerText, slugText, fullText: mentionText };
}

/**
 * Parses the text at the cursor position to detect if user is typing a mention.
 *
 * @param text - The full input text
 * @param cursorPos - Current cursor position in the text
 * @returns MentionState describing the current mention being typed, or idle state
 */
export function parseMentionAtCursor(text: string, cursorPos: number): MentionState {
  const idleState: MentionState = {
    phase: 'idle',
    startIndex: -1,
    ownerText: '',
    slugText: '',
    fullText: ''
  };

  if (!text || cursorPos < 0) return idleState;

  const atIndex = findAtSignIndex(text, cursorPos);
  if (atIndex === -1) return idleState;

  const mentionText = text.slice(atIndex, cursorPos);
  const slashIndex = mentionText.indexOf('/');

  const state =
    slashIndex === -1
      ? buildOwnerPhaseState(mentionText, atIndex)
      : buildSlugPhaseState(mentionText, atIndex, slashIndex);

  return state ?? idleState;
}

/**
 * Extracts unique owners from a list of sources.
 *
 * @param sources - Array of ChatSource objects
 * @returns Array of OwnerInfo sorted by endpoint count descending
 */
export function getUniqueOwners(sources: ChatSource[]): OwnerInfo[] {
  const ownerMap = new Map<string, number>();

  for (const source of sources) {
    if (source.owner_username) {
      const current = ownerMap.get(source.owner_username) ?? 0;
      ownerMap.set(source.owner_username, current + 1);
    }
  }

  return [...ownerMap.entries()]
    .map(([username, endpointCount]) => ({ username, endpointCount }))
    .toSorted((a, b) => b.endpointCount - a.endpointCount);
}

/**
 * Filters owners by a search query (case-insensitive).
 *
 * @param owners - Array of OwnerInfo
 * @param query - Search query to filter by
 * @param maxResults - Maximum number of results to return (default 10)
 * @returns Filtered array of OwnerInfo
 */
export function filterOwners(owners: OwnerInfo[], query: string, maxResults = 10): OwnerInfo[] {
  const trimmed = query.trim().toLowerCase();

  if (!trimmed) {
    return owners.slice(0, maxResults);
  }

  return owners
    .filter((owner) => owner.username.toLowerCase().includes(trimmed))
    .slice(0, maxResults);
}

/**
 * Gets all endpoints owned by a specific owner.
 *
 * @param sources - Array of ChatSource objects
 * @param ownerUsername - Username to filter by
 * @returns Array of ChatSource owned by the specified owner
 */
export function getEndpointsByOwner(sources: ChatSource[], ownerUsername: string): ChatSource[] {
  const normalizedOwner = ownerUsername.toLowerCase();

  return sources.filter((source) => source.owner_username?.toLowerCase() === normalizedOwner);
}

/**
 * Filters endpoints by slug or name (case-insensitive).
 *
 * @param endpoints - Array of ChatSource objects
 * @param query - Search query to filter by
 * @param maxResults - Maximum number of results to return (default 10)
 * @returns Filtered array of ChatSource
 */
export function filterEndpoints(
  endpoints: ChatSource[],
  query: string,
  maxResults = 10
): ChatSource[] {
  const trimmed = query.trim().toLowerCase();

  if (!trimmed) {
    return endpoints.slice(0, maxResults);
  }

  return endpoints
    .filter(
      (endpoint) =>
        endpoint.slug.toLowerCase().includes(trimmed) ||
        endpoint.name.toLowerCase().includes(trimmed)
    )
    .slice(0, maxResults);
}

/**
 * Replaces the mention text in the input with the completed mention.
 *
 * @param text - Original input text
 * @param startIndex - Start index of the mention (@ position)
 * @param cursorPos - Current cursor position
 * @param replacement - Text to replace the mention with
 * @returns Object with new value and new cursor position
 */
export function replaceMention(
  text: string,
  startIndex: number,
  cursorPos: number,
  replacement: string
): { newValue: string; newCursorPos: number } {
  const before = text.slice(0, startIndex);
  const after = text.slice(cursorPos);

  const newValue = before + replacement + after;
  const newCursorPos = startIndex + replacement.length;

  return { newValue, newCursorPos };
}

/**
 * Finds a complete mention that matches a valid source.
 *
 * @param sources - Array of ChatSource objects
 * @param owner - Owner username
 * @param slug - Endpoint slug
 * @returns The matching ChatSource or undefined
 */
export function findMatchingSource(
  sources: ChatSource[],
  owner: string,
  slug: string
): ChatSource | undefined {
  const normalizedOwner = owner.toLowerCase();
  const normalizedSlug = slug.toLowerCase();

  return sources.find(
    (source) =>
      source.owner_username?.toLowerCase() === normalizedOwner &&
      source.slug.toLowerCase() === normalizedSlug
  );
}

/**
 * Checks if a source is already in the selected sources.
 *
 * @param selectedIds - Set of selected source IDs
 * @param source - Source to check
 * @returns True if already selected
 */
export function isSourceAlreadySelected(selectedIds: Set<string>, source: ChatSource): boolean {
  return selectedIds.has(source.id);
}

// =============================================================================
// Mention Extraction (for sync)
// =============================================================================

/**
 * Extracts all complete @owner/slug mentions from text.
 *
 * @param text - Input text to scan
 * @returns Array of {owner, slug} objects for each complete mention found
 */
export function extractCompleteMentions(text: string): Array<{ owner: string; slug: string }> {
  const regex = /@([a-zA-Z0-9_-]+)\/([a-zA-Z0-9_-]+)/g;
  const mentions: Array<{ owner: string; slug: string }> = [];

  for (const match of text.matchAll(regex)) {
    const owner = match[1];
    const slug = match[2];
    if (owner && slug) {
      mentions.push({ owner, slug });
    }
  }

  return mentions;
}

/**
 * Gets the set of source IDs that are mentioned in the text.
 *
 * @param text - Input text to scan
 * @param sources - Available sources to match against
 * @returns Set of source IDs that have complete mentions in the text
 */
export function getMentionedSourceIds(text: string, sources: ChatSource[]): Set<string> {
  const mentions = extractCompleteMentions(text);
  const ids = new Set<string>();

  for (const mention of mentions) {
    const source = findMatchingSource(sources, mention.owner, mention.slug);
    if (source) {
      ids.add(source.id);
    }
  }

  return ids;
}
