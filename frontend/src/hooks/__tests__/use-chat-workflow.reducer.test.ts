import type { ChatStreamEvent } from '@/lib/sdk-client';
import type { ProcessingStatus } from '../use-chat-workflow';

import { describe, expect, it, vi } from 'vitest';

import { createMockSearchableChatSource } from '@/test/mocks/fixtures';
import {
  AggregatorError,
  AuthenticationError,
  EndpointResolutionError
} from '@/test/mocks/sdk-client';

import {
  extractSourceDisplayName,
  getErrorMessage,
  initialState,
  processStreamEventForStatus,
  workflowReducer
} from '../use-chat-workflow';

// Mock the SDK client module so error class instanceof checks work
vi.mock('@/lib/sdk-client', () => import('@/test/mocks/sdk-client'));

// ============================================================================
// extractSourceDisplayName
// ============================================================================

describe('extractSourceDisplayName', () => {
  it('converts slug to title case', () => {
    expect(extractSourceDisplayName('alice/my-dataset')).toBe('My Dataset');
  });

  it('handles single segment', () => {
    expect(extractSourceDisplayName('simple')).toBe('Simple');
  });

  it('handles multiple hyphens', () => {
    expect(extractSourceDisplayName('owner/a-b-c')).toBe('A B C');
  });

  it('handles path without hyphens', () => {
    expect(extractSourceDisplayName('owner/dataset')).toBe('Dataset');
  });
});

// ============================================================================
// processStreamEventForStatus
// ============================================================================

describe('processStreamEventForStatus', () => {
  it('handles retrieval_start with sources', () => {
    const event: ChatStreamEvent = { type: 'retrieval_start', sourceCount: 3 };
    const result = processStreamEventForStatus(null, event);
    expect(result?.phase).toBe('retrieving');
    expect(result?.message).toContain('3');
    expect(result?.retrieval?.total).toBe(3);
  });

  it('handles retrieval_start with zero sources', () => {
    const event: ChatStreamEvent = { type: 'retrieval_start', sourceCount: 0 };
    const result = processStreamEventForStatus(null, event);
    expect(result?.phase).toBe('retrieving');
    expect(result?.message).toBe('Preparing request…');
  });

  it('handles source_complete', () => {
    const baseStatus: ProcessingStatus = {
      phase: 'retrieving',
      message: 'Searching...',
      retrieval: { completed: 0, total: 2, documentsFound: 0 },
      completedSources: []
    };
    const event: ChatStreamEvent = {
      type: 'source_complete',
      path: 'alice/ds',
      status: 'success',
      documentsRetrieved: 5
    };
    const result = processStreamEventForStatus(baseStatus, event);
    expect(result?.retrieval?.completed).toBe(1);
    expect(result?.retrieval?.documentsFound).toBe(5);
    expect(result?.completedSources).toHaveLength(1);
    expect(result?.completedSources[0]?.path).toBe('alice/ds');
  });

  it('returns null for source_complete with null status', () => {
    const event: ChatStreamEvent = {
      type: 'source_complete',
      path: 'alice/ds',
      status: 'success',
      documentsRetrieved: 5
    };
    expect(processStreamEventForStatus(null, event)).toBeNull();
  });

  it('handles retrieval_complete', () => {
    const baseStatus: ProcessingStatus = {
      phase: 'retrieving',
      message: '',
      completedSources: []
    };
    const event: ChatStreamEvent = { type: 'retrieval_complete', totalDocuments: 10, timeMs: 500 };
    const result = processStreamEventForStatus(baseStatus, event);
    expect(result?.message).toContain('10');
    expect(result?.timing?.retrievalMs).toBe(500);
  });

  it('handles generation_start', () => {
    const baseStatus: ProcessingStatus = {
      phase: 'retrieving',
      message: '',
      completedSources: [{ path: 'a/b', displayName: 'B', status: 'success', documents: 3 }]
    };
    const event: ChatStreamEvent = { type: 'generation_start' };
    const result = processStreamEventForStatus(baseStatus, event);
    expect(result?.phase).toBe('generating');
    expect(result?.completedSources).toHaveLength(1);
  });

  it('handles token event - transitions to streaming', () => {
    const baseStatus: ProcessingStatus = {
      phase: 'generating',
      message: '',
      completedSources: []
    };
    const event: ChatStreamEvent = { type: 'token', content: 'Hello' };
    const result = processStreamEventForStatus(baseStatus, event);
    expect(result?.phase).toBe('streaming');
  });

  it('handles token event - stays in streaming if already streaming', () => {
    const baseStatus: ProcessingStatus = {
      phase: 'streaming',
      message: 'Writing...',
      completedSources: []
    };
    const event: ChatStreamEvent = { type: 'token', content: ' world' };
    const result = processStreamEventForStatus(baseStatus, event);
    // Should return same status since already streaming
    expect(result).toBe(baseStatus);
  });

  it('handles done event', () => {
    const baseStatus: ProcessingStatus = {
      phase: 'streaming',
      message: '',
      completedSources: []
    };
    const event: ChatStreamEvent = {
      type: 'done',
      sources: {},
      retrievalInfo: [],
      metadata: { retrievalTimeMs: 100, generationTimeMs: 200, totalTimeMs: 300 }
    };
    expect(processStreamEventForStatus(baseStatus, event)).toBeNull();
  });

  it('handles error event', () => {
    const event: ChatStreamEvent = { type: 'error', message: 'Something failed' };
    const result = processStreamEventForStatus(null, event);
    expect(result?.phase).toBe('error');
    expect(result?.message).toBe('Something failed');
  });
});

// ============================================================================
// getErrorMessage
// ============================================================================

describe('getErrorMessage', () => {
  it('handles AuthenticationError', () => {
    expect(getErrorMessage(new AuthenticationError())).toBe(
      'Authentication required. Please log in again.'
    );
  });

  it('handles AggregatorError', () => {
    expect(getErrorMessage(new AggregatorError('timeout'))).toBe('Chat service error: timeout');
  });

  it('handles EndpointResolutionError', () => {
    expect(getErrorMessage(new EndpointResolutionError('not found'))).toBe(
      'Could not resolve endpoint: not found'
    );
  });

  it('handles generic Error', () => {
    expect(getErrorMessage(new Error('Something broke'))).toBe('Something broke');
  });

  it('handles non-Error values', () => {
    expect(getErrorMessage('string error')).toBe('An unexpected error occurred');
  });
});

// ============================================================================
// workflowReducer
// ============================================================================

describe('workflowReducer', () => {
  it('starts in idle phase', () => {
    expect(initialState.phase).toBe('idle');
    expect(initialState.query).toBeNull();
  });

  it('START_SEARCH transitions to searching', () => {
    const state = workflowReducer(initialState, { type: 'START_SEARCH', query: 'test' });
    expect(state.phase).toBe('searching');
    expect(state.query).toBe('test');
  });

  it('SEARCH_COMPLETE transitions to selecting', () => {
    const searchState = { ...initialState, phase: 'searching' as const, query: 'test' };
    const endpoints = [createMockSearchableChatSource()];
    const state = workflowReducer(searchState, {
      type: 'SEARCH_COMPLETE',
      endpoints
    });
    expect(state.phase).toBe('selecting');
    expect(state.suggestedEndpoints).toEqual(endpoints);
  });

  it('TOGGLE_SOURCE adds source', () => {
    const state = workflowReducer(initialState, { type: 'TOGGLE_SOURCE', id: 'source-1' });
    expect(state.selectedSources.has('source-1')).toBe(true);
  });

  it('TOGGLE_SOURCE removes existing source', () => {
    const stateWithSource = {
      ...initialState,
      selectedSources: new Set(['source-1'])
    };
    const state = workflowReducer(stateWithSource, { type: 'TOGGLE_SOURCE', id: 'source-1' });
    expect(state.selectedSources.has('source-1')).toBe(false);
  });

  it('START_PREPARING transitions to preparing', () => {
    const state = workflowReducer(initialState, { type: 'START_PREPARING' });
    expect(state.phase).toBe('preparing');
  });

  it('START_STREAMING transitions to streaming', () => {
    const status: ProcessingStatus = {
      phase: 'retrieving',
      message: 'Starting...',
      completedSources: []
    };
    const state = workflowReducer(initialState, { type: 'START_STREAMING', status });
    expect(state.phase).toBe('streaming');
    expect(state.processingStatus).toEqual(status);
  });

  it('UPDATE_CONTENT accumulates content', () => {
    const state = workflowReducer(initialState, {
      type: 'UPDATE_CONTENT',
      content: 'Hello world'
    });
    expect(state.streamedContent).toBe('Hello world');
  });

  it('COMPLETE transitions to complete', () => {
    const sources = { 'doc.md': { slug: 'ds', content: 'content' } };
    const state = workflowReducer(initialState, { type: 'COMPLETE', sources });
    expect(state.phase).toBe('complete');
    expect(state.aggregatorSources).toEqual(sources);
    expect(state.processingStatus).toBeNull();
  });

  it('ERROR transitions to error', () => {
    const state = workflowReducer(initialState, { type: 'ERROR', error: 'Something failed' });
    expect(state.phase).toBe('error');
    expect(state.error).toBe('Something failed');
  });

  it('RESET returns to initial state', () => {
    const errorState = { ...initialState, phase: 'error' as const, error: 'oops' };
    const state = workflowReducer(errorState, { type: 'RESET' });
    expect(state.phase).toBe('idle');
    expect(state.error).toBeNull();
  });
});
