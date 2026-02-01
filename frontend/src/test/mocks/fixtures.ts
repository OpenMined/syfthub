/**
 * Test data factory functions.
 * Each accepts Partial<T> overrides for flexible test setup.
 */

import type { SearchableChatSource } from '@/lib/search-service';
import type { AccountingTransaction, AccountingUser, ChatSource, User } from '@/lib/types';

// ============================================================================
// User Fixtures
// ============================================================================

export function createMockUser(overrides: Partial<User> = {}): User {
  return {
    id: '1',
    username: 'testuser',
    email: 'test@example.com',
    name: 'Test User',
    full_name: 'Test User',
    avatar_url: 'https://example.com/avatar.png',
    role: 'user',
    is_active: true,
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
    ...overrides
  };
}

export function createMockSdkUser(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    username: 'testuser',
    email: 'test@example.com',
    fullName: 'Test User',
    avatarUrl: 'https://example.com/avatar.png',
    role: 'user' as const,
    isActive: true,
    createdAt: new Date('2024-01-01T00:00:00.000Z'),
    updatedAt: new Date('2024-01-01T00:00:00.000Z'),
    domain: null,
    aggregatorUrl: null,
    ...overrides
  };
}

// ============================================================================
// ChatSource Fixtures
// ============================================================================

export function createMockChatSource(overrides: Partial<ChatSource> = {}): ChatSource {
  return {
    id: 'test-source',
    name: 'Test Source',
    tags: ['test'],
    description: 'A test data source',
    type: 'data_source',
    updated: '2 days ago',
    status: 'active',
    slug: 'test-source',
    stars_count: 5,
    version: '1.0.0',
    readme: 'Test readme content',
    contributors_count: 2,
    owner_username: 'testowner',
    full_path: 'testowner/test-source',
    ...overrides
  };
}

export function createMockSearchableChatSource(
  overrides: Partial<SearchableChatSource> = {}
): SearchableChatSource {
  return {
    ...createMockChatSource(),
    relevance_score: 0.8,
    ...overrides
  };
}

// ============================================================================
// Accounting Fixtures
// ============================================================================

export function createMockAccountingUser(overrides: Partial<AccountingUser> = {}): AccountingUser {
  return {
    id: 'acc-1',
    email: 'test@example.com',
    balance: 500,
    organization: null,
    ...overrides
  };
}

export function createMockAccountingTransaction(
  overrides: Partial<AccountingTransaction> = {}
): AccountingTransaction {
  return {
    id: 'tx-1',
    senderEmail: 'sender@example.com',
    recipientEmail: 'recipient@example.com',
    amount: 100,
    status: 'completed',
    createdBy: 'sender',
    resolvedBy: 'recipient',
    createdAt: new Date('2024-01-15T10:00:00.000Z'),
    resolvedAt: new Date('2024-01-15T10:05:00.000Z'),
    appName: null,
    appEpPath: null,
    ...overrides
  };
}
