// vi.mock so that getErrorMessage's `instanceof` checks resolve against the
// same class definitions we imported above.
import { describe, expect, it, vi } from 'vitest';

import {
  AggregatorError,
  AuthenticationError,
  EndpointResolutionError
} from '@/test/mocks/sdk-client';

// Must import via the mock path since vi.mock in the main test file rewires
// '@/lib/sdk-client' → '@/test/mocks/sdk-client'. But getErrorMessage uses
// instanceof against the SDK's real classes. In this dedicated unit test we
// import getErrorMessage directly and construct errors from the same mock
// classes that the vi.mock wiring would provide.
//
// Because getErrorMessage is a pure function that only relies on `instanceof`
// and property access, we can test it without rendering a hook or setting up
// providers.

import { getErrorMessage } from '../use-chat-workflow';

vi.mock('@/lib/sdk-client', () => import('@/test/mocks/sdk-client'));

// ============================================================================
// AuthenticationError
// ============================================================================

describe('getErrorMessage', () => {
  describe('AuthenticationError', () => {
    it('returns auth message', () => {
      const error = new AuthenticationError('Session expired');
      expect(getErrorMessage(error)).toBe('Authentication required. Please log in again.');
    });
  });

  // ==========================================================================
  // AggregatorError — structured error_code path
  // ==========================================================================

  describe('AggregatorError with structured error_code', () => {
    it('returns credit message for error_code "insufficient_credits"', () => {
      const error = new AggregatorError('Forbidden', 403, {
        error_code: 'insufficient_credits'
      });
      expect(getErrorMessage(error)).toBe(
        'Insufficient credits. Purchase more bundles from the endpoint detail page.'
      );
    });

    it('returns credit message for error_code "policy_blocked"', () => {
      const error = new AggregatorError('Forbidden', 403, {
        error_code: 'policy_blocked'
      });
      expect(getErrorMessage(error)).toBe(
        'Insufficient credits. Purchase more bundles from the endpoint detail page.'
      );
    });

    it('does NOT return credit message for unknown error_code on 403', () => {
      const error = new AggregatorError('Forbidden', 403, {
        error_code: 'rate_limited'
      });
      // Falls through to string heuristic, which won't match either
      expect(getErrorMessage(error)).toBe('Chat service error: Forbidden');
    });

    it('does NOT return credit message for 500 with insufficient_credits code', () => {
      const error = new AggregatorError('Server error', 500, {
        error_code: 'insufficient_credits'
      });
      // Only 403 triggers the credit check
      expect(getErrorMessage(error)).toBe('Chat service error: Server error');
    });
  });

  // ==========================================================================
  // AggregatorError — string heuristic path
  // ==========================================================================

  describe('AggregatorError with string heuristic (fallback)', () => {
    it('matches when BOTH blocking + credit keywords are present in detail', () => {
      const error = new AggregatorError('Error', 403, 'Insufficient credit balance');
      expect(getErrorMessage(error)).toBe(
        'Insufficient credits. Purchase more bundles from the endpoint detail page.'
      );
    });

    it('matches "blocked" + "bundle" combination', () => {
      const error = new AggregatorError('Error', 403, 'Request blocked: no bundle active');
      expect(getErrorMessage(error)).toBe(
        'Insufficient credits. Purchase more bundles from the endpoint detail page.'
      );
    });

    it('falls back to message when detail is not a string', () => {
      const error = new AggregatorError('blocked request insufficient credit', 403, 42);
      expect(getErrorMessage(error)).toBe(
        'Insufficient credits. Purchase more bundles from the endpoint detail page.'
      );
    });

    it('does NOT match with only a blocking keyword (no credit keyword)', () => {
      const error = new AggregatorError('Error', 403, 'Request blocked by policy');
      expect(getErrorMessage(error)).toBe('Chat service error: Error');
    });

    it('does NOT match with only a credit keyword (no blocking keyword)', () => {
      const error = new AggregatorError('Error', 403, 'Please purchase a credit bundle');
      expect(getErrorMessage(error)).toBe('Chat service error: Error');
    });

    it('does NOT match for non-403 status even with both keywords', () => {
      const error = new AggregatorError('Error', 500, 'Insufficient credit balance');
      expect(getErrorMessage(error)).toBe('Chat service error: Error');
    });
  });

  // ==========================================================================
  // AggregatorError — generic
  // ==========================================================================

  describe('AggregatorError — generic (non-403)', () => {
    it('returns chat service error with message', () => {
      const error = new AggregatorError('Model timeout', 504);
      expect(getErrorMessage(error)).toBe('Chat service error: Model timeout');
    });

    it('returns chat service error for 403 without matching keywords', () => {
      const error = new AggregatorError('Access denied', 403);
      expect(getErrorMessage(error)).toBe('Chat service error: Access denied');
    });
  });

  // ==========================================================================
  // EndpointResolutionError
  // ==========================================================================

  describe('EndpointResolutionError', () => {
    it('returns resolution error message', () => {
      const error = new EndpointResolutionError('Endpoint not found');
      expect(getErrorMessage(error)).toBe('Could not resolve endpoint: Endpoint not found');
    });
  });

  // ==========================================================================
  // Other errors
  // ==========================================================================

  describe('other error types', () => {
    it('returns message from generic Error', () => {
      const error = new Error('Something broke');
      expect(getErrorMessage(error)).toBe('Something broke');
    });

    it('returns fallback for non-Error values', () => {
      expect(getErrorMessage('a string')).toBe('An unexpected error occurred');
      expect(getErrorMessage(42)).toBe('An unexpected error occurred');
      expect(getErrorMessage(null)).toBe('An unexpected error occurred');
      // eslint-disable-next-line unicorn/no-useless-undefined -- testing explicit undefined input
      expect(getErrorMessage(undefined)).toBe('An unexpected error occurred');
    });
  });
});
