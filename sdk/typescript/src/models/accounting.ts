/**
 * Accounting Models (MPP Wallet)
 *
 * Models for the MPP wallet system. Replaces the previous external accounting
 * service models with wallet-based types for the Micropayment Protocol.
 */

// =============================================================================
// Wallet Types
// =============================================================================

/**
 * Wallet information for the current user.
 */
export interface WalletInfo {
  /** Wallet address (null if no wallet configured) */
  address: string | null;
  /** Whether a wallet exists for this user */
  exists: boolean;
}

/**
 * Wallet balance and recent activity.
 */
export interface WalletBalance {
  /** Current balance amount */
  balance: number;
  /** Currency identifier */
  currency: string;
  /** Recent transactions for this wallet */
  recent_transactions: WalletTransaction[];
  /** Whether a wallet is configured */
  wallet_configured: boolean;
}

/**
 * A wallet transaction record.
 */
export interface WalletTransaction {
  /** Unique transaction identifier */
  id: string;
  /** Email of the sender */
  sender_email: string;
  /** Email of the recipient */
  recipient_email: string;
  /** Transaction amount */
  amount: number;
  /** Transaction status (e.g., "completed", "pending") */
  status: string;
  /** When the transaction was created (ISO 8601) */
  created_at: string;
  /** App name associated with the transaction */
  app_name?: string;
  /** Endpoint path associated with the transaction */
  app_ep_path?: string;
}

// =============================================================================
// Backward Compatibility Types
// =============================================================================

/**
 * Response from transaction tokens endpoint.
 *
 * @deprecated Transaction tokens are no longer used. Payments are handled
 * via the MPP 402 flow. Kept for backward compatibility with getTransactionTokens().
 */
export interface TransactionTokensResponse {
  /** Mapping of owner_username to transaction token */
  tokens: Record<string, string>;
  /** Mapping of owner_username to error message (for failed tokens) */
  errors: Record<string, string>;
}
