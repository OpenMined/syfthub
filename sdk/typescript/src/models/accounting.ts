/**
 * Accounting Models
 *
 * Models for the external accounting service. The accounting service manages
 * user balances and transactions, and uses its own authentication separate
 * from SyftHub.
 */

// =============================================================================
// Enums
// =============================================================================

/**
 * Transaction status in the accounting service.
 */
export const TransactionStatus = {
  /** Transaction created, awaiting confirmation */
  PENDING: 'pending',
  /** Transaction confirmed, funds transferred */
  COMPLETED: 'completed',
  /** Transaction cancelled, no funds transferred */
  CANCELLED: 'cancelled',
} as const;

export type TransactionStatus = (typeof TransactionStatus)[keyof typeof TransactionStatus];

/**
 * Who created or resolved a transaction.
 */
export const CreatorType = {
  /** System-initiated transaction */
  SYSTEM: 'system',
  /** Sender-initiated transaction */
  SENDER: 'sender',
  /** Recipient-initiated transaction (delegated) */
  RECIPIENT: 'recipient',
} as const;

export type CreatorType = (typeof CreatorType)[keyof typeof CreatorType];

// =============================================================================
// Core Models
// =============================================================================

/**
 * User from accounting service with balance.
 *
 * This represents the user's account in the external accounting service,
 * which is separate from the SyftHub user account.
 */
export interface AccountingUser {
  readonly id: string;
  readonly email: string;
  readonly balance: number;
  readonly organization: string | null;
}

/**
 * Transaction record from accounting service.
 *
 * Transactions go through a lifecycle:
 * 1. Created (status=PENDING)
 * 2. Confirmed or Cancelled (status=COMPLETED or CANCELLED)
 *
 * The createdBy field indicates who initiated the transaction:
 * - SENDER: Direct transaction by the payer
 * - RECIPIENT: Delegated transaction using a token
 * - SYSTEM: System-initiated transaction
 *
 * The resolvedBy field indicates who confirmed/cancelled.
 */
export interface Transaction {
  readonly id: string;
  readonly senderEmail: string;
  readonly recipientEmail: string;
  readonly amount: number;
  readonly status: TransactionStatus;
  readonly createdBy: CreatorType;
  readonly resolvedBy: CreatorType | null;
  readonly createdAt: Date;
  readonly resolvedAt: Date | null;
  readonly appName: string | null;
  readonly appEpPath: string | null;
}

// =============================================================================
// Input Types
// =============================================================================

/**
 * Input for creating a direct transaction.
 */
export interface CreateTransactionInput {
  /** Email of the recipient */
  recipientEmail: string;
  /** Amount to transfer (must be > 0) */
  amount: number;
  /** Optional app name for context (e.g., "syftai-space") */
  appName?: string;
  /** Optional endpoint path for context (e.g., "alice/model") */
  appEpPath?: string;
}

/**
 * Input for creating a delegated transaction.
 */
export interface CreateDelegatedTransactionInput {
  /** Email of the sender who created the token */
  senderEmail: string;
  /** Amount to transfer (must be > 0) */
  amount: number;
  /** JWT token from sender's createTransactionToken() */
  token: string;
}

/**
 * Input for updating password.
 */
export interface UpdatePasswordInput {
  /** Current password for verification */
  currentPassword: string;
  /** New password to set */
  newPassword: string;
}

// =============================================================================
// Response Types (from API)
// =============================================================================

/**
 * Raw transaction response from API (before date parsing).
 */
export interface TransactionResponse {
  id: string;
  senderEmail: string;
  recipientEmail: string;
  amount: number;
  status: TransactionStatus;
  createdBy: CreatorType;
  resolvedBy: CreatorType | null;
  createdAt: string;
  resolvedAt: string | null;
  appName: string | null;
  appEpPath: string | null;
}

/**
 * Token response from createTransactionToken.
 */
export interface TransactionTokenResponse {
  token: string;
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Parse a transaction response into a Transaction object.
 */
export function parseTransaction(response: TransactionResponse): Transaction {
  return {
    ...response,
    createdAt: new Date(response.createdAt),
    resolvedAt: response.resolvedAt ? new Date(response.resolvedAt) : null,
  };
}

/**
 * Check if a transaction is pending.
 */
export function isTransactionPending(tx: Transaction): boolean {
  return tx.status === TransactionStatus.PENDING;
}

/**
 * Check if a transaction is completed.
 */
export function isTransactionCompleted(tx: Transaction): boolean {
  return tx.status === TransactionStatus.COMPLETED;
}

/**
 * Check if a transaction is cancelled.
 */
export function isTransactionCancelled(tx: Transaction): boolean {
  return tx.status === TransactionStatus.CANCELLED;
}
