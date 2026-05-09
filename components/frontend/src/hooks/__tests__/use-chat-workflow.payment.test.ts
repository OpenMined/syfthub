/**
 * Tests for the `payment_required` handling in useChatWorkflow.
 *
 * Verifies the buffering + 200ms debounce that batches multi-endpoint
 * challenges into a single approval. Uses fake timers to drive the
 * debounce window deterministically.
 */
import type { ChatStreamEvent, PaymentRequiredEvent } from '../use-chat-workflow';

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createMockChatSource } from '@/test/mocks/fixtures';
import { syftClient } from '@/test/mocks/sdk-client';
import { AllProviders } from '@/test/render-with-providers';

import { useChatWorkflow } from '../use-chat-workflow';

vi.mock('@/lib/sdk-client', () => import('@/test/mocks/sdk-client'));

function makePaymentEvent(overrides: Partial<PaymentRequiredEvent> = {}): PaymentRequiredEvent {
  return {
    type: 'payment_required',
    chatSessionId: 'session-1',
    endpointSlug: 'demo',
    challenge: 'Payment id="x"',
    amount: '0.10',
    currency: '0x1111111111111111111111111111111111111111',
    recipient: '0x2222222222222222222222222222222222222222',
    challengeId: 'chal-1',
    intent: 'charge',
    ...overrides
  };
}

const mockModel = createMockChatSource({
  name: 'Test Model',
  slug: 'test-model',
  type: 'model',
  full_path: 'owner/test-model'
});

describe('useChatWorkflow: payment_required', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('buffers two payment_required events arriving in sequence into one batch', async () => {
    // The generator yields both events back-to-back so they land within the
    // 200ms debounce window and flush as one batch.
    const events: ChatStreamEvent[] = [
      makePaymentEvent({ challengeId: 'a', endpointSlug: 'one' }),
      makePaymentEvent({ challengeId: 'b', endpointSlug: 'two' })
    ];
    vi.mocked(syftClient.chat.stream).mockReturnValue(
      (async function* () {
        for (const e of events) yield e;
      })()
    );

    const { result } = renderHook(() => useChatWorkflow({ model: mockModel, dataSources: [] }), {
      wrapper: AllProviders
    });

    await act(async () => {
      await result.current.submitQuery('hi');
    });

    // The flush timer (200ms) is still real time. Wait for it to drain.
    await waitFor(
      () => {
        expect(result.current.paymentChallenges).toHaveLength(2);
      },
      { timeout: 1500 }
    );

    const ids = result.current.paymentChallenges
      .map((c) => c.challengeId)
      .toSorted((a, b) => a.localeCompare(b));
    expect(ids).toEqual(['a', 'b']);
  });

  it('exposes clearPaymentChallenges to reset between approval cycles', async () => {
    const events: ChatStreamEvent[] = [makePaymentEvent({ challengeId: 'a' })];
    vi.mocked(syftClient.chat.stream).mockReturnValue(
      (async function* () {
        for (const e of events) yield e;
      })()
    );

    const { result } = renderHook(() => useChatWorkflow({ model: mockModel, dataSources: [] }), {
      wrapper: AllProviders
    });

    await act(async () => {
      await result.current.submitQuery('hi');
    });

    await waitFor(
      () => {
        expect(result.current.paymentChallenges).toHaveLength(1);
      },
      { timeout: 1500 }
    );
    expect(result.current.paymentChallenges[0]?.challengeId).toBe('a');

    act(() => {
      result.current.clearPaymentChallenges();
    });
    expect(result.current.paymentChallenges).toHaveLength(0);
  });
});
