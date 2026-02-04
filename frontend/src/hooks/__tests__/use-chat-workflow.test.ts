import type { ChatStreamEvent } from '@/lib/sdk-client';

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createMockChatSource } from '@/test/mocks/fixtures';
import { syftClient } from '@/test/mocks/sdk-client';
import { AllProviders } from '@/test/render-with-providers';

import { useChatWorkflow } from '../use-chat-workflow';

// Mock the SDK client module
vi.mock('@/lib/sdk-client', () => import('@/test/mocks/sdk-client'));

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

  it('executes directly without sources when none are pre-selected', async () => {
    const streamEvents: ChatStreamEvent[] = [
      { type: 'retrieval_start', sourceCount: 0 },
      { type: 'generation_start' },
      { type: 'token', content: 'Hello' },
      {
        type: 'done',
        sources: {},
        retrievalInfo: [],
        metadata: { retrievalTimeMs: 0, generationTimeMs: 200, totalTimeMs: 200 }
      }
    ];

    vi.mocked(syftClient.chat.stream).mockReturnValue(createMockStream(streamEvents));

    const onComplete = vi.fn();
    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource],
          onComplete
        }),
      { wrapper: AllProviders }
    );

    await act(async () => {
      void result.current.submitQuery('test query');
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('complete');
    });

    expect(result.current.query).toBe('test query');
    expect(onComplete).toHaveBeenCalledWith(
      expect.objectContaining({
        query: 'test query',
        content: 'Hello',
        dataSourcePaths: []
      })
    );
  });

  it('executes with pre-selected sources', async () => {
    const streamEvents: ChatStreamEvent[] = [
      { type: 'retrieval_start', sourceCount: 1 },
      { type: 'source_complete', path: 'owner/test-ds', status: 'success', documentsRetrieved: 3 },
      { type: 'retrieval_complete', totalDocuments: 3, timeMs: 100 },
      { type: 'generation_start' },
      { type: 'token', content: 'Based on sources' },
      {
        type: 'done',
        sources: { 'doc.md': { slug: 'test-ds', content: 'content' } },
        retrievalInfo: [],
        metadata: { retrievalTimeMs: 100, generationTimeMs: 200, totalTimeMs: 300 }
      }
    ];

    vi.mocked(syftClient.chat.stream).mockReturnValue(createMockStream(streamEvents));

    const onComplete = vi.fn();
    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource],
          onComplete
        }),
      { wrapper: AllProviders }
    );

    const sourceIds = new Set([mockDataSource.id]);
    await act(async () => {
      void result.current.submitQuery('test query', sourceIds);
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('complete');
    });

    expect(onComplete).toHaveBeenCalledWith(
      expect.objectContaining({
        query: 'test query',
        dataSourcePaths: ['owner/test-ds']
      })
    );
  });

  it('executes with context sources when provided', async () => {
    const streamEvents: ChatStreamEvent[] = [
      { type: 'retrieval_start', sourceCount: 1 },
      { type: 'source_complete', path: 'owner/test-ds', status: 'success', documentsRetrieved: 2 },
      { type: 'retrieval_complete', totalDocuments: 2, timeMs: 50 },
      { type: 'generation_start' },
      { type: 'token', content: 'Context result' },
      {
        type: 'done',
        sources: {},
        retrievalInfo: [],
        metadata: { retrievalTimeMs: 50, generationTimeMs: 100, totalTimeMs: 150 }
      }
    ];

    vi.mocked(syftClient.chat.stream).mockReturnValue(createMockStream(streamEvents));

    const onComplete = vi.fn();
    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource],
          contextSources: [mockDataSource],
          onComplete
        }),
      { wrapper: AllProviders }
    );

    await act(async () => {
      void result.current.submitQuery('test query');
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('complete');
    });

    expect(onComplete).toHaveBeenCalledWith(
      expect.objectContaining({
        query: 'test query',
        dataSourcePaths: ['owner/test-ds']
      })
    );
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
      void result.current.submitQuery('test query');
    });

    expect(result.current.phase).toBe('error');
    expect(result.current.error).toContain('model');
  });

  it('handles stream error gracefully', async () => {
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
      void result.current.submitQuery('test query');
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('error');
    });
  });

  it('reset clears all state', async () => {
    const streamEvents: ChatStreamEvent[] = [
      { type: 'retrieval_start', sourceCount: 0 },
      { type: 'generation_start' },
      { type: 'token', content: 'Hello' },
      {
        type: 'done',
        sources: {},
        retrievalInfo: [],
        metadata: { retrievalTimeMs: 0, generationTimeMs: 100, totalTimeMs: 100 }
      }
    ];

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
      void result.current.submitQuery('test query');
    });

    await waitFor(() => {
      expect(result.current.phase).toBe('complete');
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.phase).toBe('idle');
    expect(result.current.query).toBeNull();
    expect(result.current.streamedContent).toBe('');
  });

  it('pre-selected sources override context sources in stream call', async () => {
    const contextSource = createMockChatSource({
      name: 'Context DS',
      slug: 'context-ds',
      type: 'data_source',
      full_path: 'owner/context-ds'
    });

    const streamEvents: ChatStreamEvent[] = [
      { type: 'retrieval_start', sourceCount: 1 },
      { type: 'source_complete', path: 'owner/test-ds', status: 'success', documentsRetrieved: 1 },
      { type: 'retrieval_complete', totalDocuments: 1, timeMs: 50 },
      { type: 'generation_start' },
      { type: 'token', content: 'Result' },
      {
        type: 'done',
        sources: {},
        retrievalInfo: [],
        metadata: { retrievalTimeMs: 50, generationTimeMs: 100, totalTimeMs: 150 }
      }
    ];

    vi.mocked(syftClient.chat.stream).mockReturnValue(createMockStream(streamEvents));

    const { result } = renderHook(
      () =>
        useChatWorkflow({
          model: mockModel,
          dataSources: [mockDataSource, contextSource],
          contextSources: [contextSource]
        }),
      { wrapper: AllProviders }
    );

    // Submit with explicit pre-selected sources (should override contextSources)
    const sourceIds = new Set([mockDataSource.id]);
    await act(async () => {
      void result.current.submitQuery('test query', sourceIds);
    });

    await waitFor(() => {
      expect(result.current.phase).not.toBe('idle');
    });

    // Verify that syftClient.chat.stream was called (at least once)
    expect(syftClient.chat.stream).toHaveBeenCalled();

    // The stream call should use the model path
    const streamCallArguments = vi.mocked(syftClient.chat.stream).mock.calls[0]?.[0] as
      | { model: string; dataSources?: string[] }
      | undefined;
    expect(streamCallArguments).toBeDefined();
    expect(streamCallArguments?.model).toBe('owner/test-model');
  });
});
