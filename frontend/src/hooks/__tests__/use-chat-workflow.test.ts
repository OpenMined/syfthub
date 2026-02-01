import type { ChatStreamEvent } from '@/lib/sdk-client';

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { searchDataSources } from '@/lib/search-service';
import { createMockChatSource, createMockSearchableChatSource } from '@/test/mocks/fixtures';
import { syftClient } from '@/test/mocks/sdk-client';
import { AllProviders } from '@/test/render-with-providers';

import { useChatWorkflow } from '../use-chat-workflow';

// Mock the SDK client module
vi.mock('@/lib/sdk-client', () => import('@/test/mocks/sdk-client'));

// Mock search service
vi.mock('@/lib/search-service', () => ({
  searchEndpoints: vi.fn().mockResolvedValue([]),
  searchDataSources: vi.fn().mockResolvedValue([]),
  searchModels: vi.fn().mockResolvedValue([]),
  filterByRelevance: vi.fn((results: unknown[]) => results),
  categorizeResults: vi.fn((results: unknown[]) => ({ highRelevance: results })),
  hasHighRelevanceResults: vi.fn().mockReturnValue(false),
  HIGH_RELEVANCE_THRESHOLD: 0.5,
  MIN_QUERY_LENGTH: 3,
  DEFAULT_TOP_K: 10
}));

// Helper to create an async generator
function createMockStream(events: ChatStreamEvent[]): AsyncGenerator<ChatStreamEvent> {
  return (async function* () {
    for (const event of events) {
      yield event;
    }
  })();
}

describe('useChatWorkflow', () => {
  const mockModel = createMockChatSource({
    name: 'Test Model',
    slug: 'test-model',
    type: 'model',
    full_path: 'owner/test-model',
    url: 'https://example.com',
    tenant_name: 'test'
  });

  const mockDataSource = createMockChatSource({
    name: 'Test DS',
    slug: 'test-ds',
    type: 'data_source',
    full_path: 'owner/test-ds'
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('starts in idle phase', () => {
    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource]
        }),
      { wrapper: AllProviders }
    );

    expect(result.current.phase).toBe('idle');
    expect(result.current.query).toBeNull();
    expect(result.current.streamedContent).toBe('');
  });

  it('transitions to searching on submitQuery', async () => {
    const mockSearchResults = [
      createMockSearchableChatSource({ slug: 'result-1', relevance_score: 0.8 })
    ];
    vi.mocked(searchDataSources).mockResolvedValue(mockSearchResults);

    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource]
        }),
      { wrapper: AllProviders }
    );

    await act(async () => {
      result.current.submitQuery('test query');
    });

    expect(result.current.phase).toBe('searching');
    expect(result.current.query).toBe('test query');

    // Wait for search to complete
    await waitFor(() => {
      expect(result.current.phase).toBe('selecting');
    });
  });

  it('skips search for short query and goes to selecting with empty results', async () => {
    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource]
        }),
      { wrapper: AllProviders }
    );

    await act(async () => {
      result.current.submitQuery('ab');
    });

    // Short queries skip the search and go directly to selecting
    await waitFor(() => {
      expect(result.current.phase).toBe('selecting');
    });
    // Search shouldn't have been called for short query
    expect(searchDataSources).not.toHaveBeenCalled();
  });

  it('ignores empty query and stays idle', async () => {
    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource]
        }),
      { wrapper: AllProviders }
    );

    await act(async () => {
      await result.current.submitQuery('   ');
    });

    // Empty queries are silently ignored - stay in idle
    expect(result.current.phase).toBe('idle');
  });

  it('errors when no model is selected', async () => {
    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: null as never,
          dataSources: [mockDataSource]
        }),
      { wrapper: AllProviders }
    );

    await act(async () => {
      result.current.submitQuery('test query');
    });

    expect(result.current.phase).toBe('error');
    expect(result.current.error).toContain('model');
  });

  it('toggleSource adds and removes sources', async () => {
    vi.mocked(searchDataSources).mockResolvedValue([]);

    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource]
        }),
      { wrapper: AllProviders }
    );

    // Submit to get to selecting phase
    await act(async () => {
      result.current.submitQuery('test query');
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('selecting');
    });

    // Toggle on
    act(() => {
      result.current.toggleSource('source-1');
    });
    expect(result.current.selectedSources.has('source-1')).toBe(true);

    // Toggle off
    act(() => {
      result.current.toggleSource('source-1');
    });
    expect(result.current.selectedSources.has('source-1')).toBe(false);
  });

  it('confirmSelection transitions through streaming to complete', async () => {
    vi.mocked(searchDataSources).mockResolvedValue([]);

    const onComplete = vi.fn();
    const streamEvents: ChatStreamEvent[] = [
      { type: 'retrieval_start', sourceCount: 1 },
      { type: 'source_complete', path: 'owner/test-ds', status: 'success', documentsRetrieved: 3 },
      { type: 'retrieval_complete', totalDocuments: 3, timeMs: 100 },
      { type: 'generation_start' },
      { type: 'token', content: 'Hello ' },
      { type: 'token', content: 'world' },
      {
        type: 'done',
        sources: { 'doc.md': { slug: 'test-ds', content: 'content' } },
        retrievalInfo: [],
        metadata: { retrievalTimeMs: 100, generationTimeMs: 200, totalTimeMs: 300 }
      }
    ];

    vi.mocked(syftClient.chat.stream).mockReturnValue(createMockStream(streamEvents));

    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource],
          onComplete
        }),
      { wrapper: AllProviders }
    );

    // Submit query
    await act(async () => {
      result.current.submitQuery('test query');
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('selecting');
    });

    // Confirm selection
    await act(async () => {
      result.current.confirmSelection();
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('complete');
    });

    expect(result.current.streamedContent).toContain('Hello ');
    expect(result.current.streamedContent).toContain('world');
  });

  it('handles search failure gracefully', async () => {
    vi.mocked(searchDataSources).mockRejectedValue(new Error('Search failed'));

    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource]
        }),
      { wrapper: AllProviders }
    );

    await act(async () => {
      result.current.submitQuery('test query');
    });

    // Should still transition to selecting with empty results
    await waitFor(() => {
      expect(result.current.phase).toBe('selecting');
    });
  });

  it('reset clears all state', async () => {
    vi.mocked(searchDataSources).mockResolvedValue([]);

    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource]
        }),
      { wrapper: AllProviders }
    );

    await act(async () => {
      result.current.submitQuery('test query');
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('selecting');
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.phase).toBe('idle');
    expect(result.current.query).toBeNull();
    expect(result.current.streamedContent).toBe('');
  });

  it('cancelSelection resets to idle', async () => {
    vi.mocked(searchDataSources).mockResolvedValue([]);

    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource]
        }),
      { wrapper: AllProviders }
    );

    await act(async () => {
      result.current.submitQuery('test query');
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('selecting');
    });

    act(() => {
      result.current.cancelSelection();
    });

    expect(result.current.phase).toBe('idle');
  });

  it('handles stream error gracefully', async () => {
    vi.mocked(searchDataSources).mockResolvedValue([]);

    const streamEvents: ChatStreamEvent[] = [{ type: 'error', message: 'Generation failed' }];

    vi.mocked(syftClient.chat.stream).mockReturnValue(createMockStream(streamEvents));

    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource]
        }),
      { wrapper: AllProviders }
    );

    await act(async () => {
      result.current.submitQuery('test query');
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('selecting');
    });

    await act(async () => {
      result.current.confirmSelection();
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('error');
    });
  });
});
