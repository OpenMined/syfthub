/**
 * Type-safe Identifiers
 *
 * Uses branded types to prevent mixing up different ID types at compile time.
 */

// Branded type helper
declare const brand: unique symbol;
type Brand<T, B> = T & { [brand]: B };

// Entity identifiers
export type AccountId = Brand<string, 'AccountId'>;
export type TransactionId = Brand<string, 'TransactionId'>;
export type LedgerEntryId = Brand<string, 'LedgerEntryId'>;
export type PaymentMethodId = Brand<string, 'PaymentMethodId'>;
export type WebhookId = Brand<string, 'WebhookId'>;
export type UserId = Brand<string, 'UserId'>;
export type ApiTokenId = Brand<string, 'ApiTokenId'>;

// Special identifiers
export type IdempotencyKey = Brand<string, 'IdempotencyKey'>;
export type ExternalReference = Brand<string, 'ExternalReference'>;

// Factory functions for creating identifiers
export const AccountId = {
  from(value: string): AccountId {
    if (!value || value.trim() === '') {
      throw new Error('AccountId cannot be empty');
    }
    return value as AccountId;
  },
  generate(): AccountId {
    return crypto.randomUUID() as AccountId;
  },
};

export const TransactionId = {
  from(value: string): TransactionId {
    if (!value || value.trim() === '') {
      throw new Error('TransactionId cannot be empty');
    }
    return value as TransactionId;
  },
  generate(): TransactionId {
    return crypto.randomUUID() as TransactionId;
  },
};

export const LedgerEntryId = {
  from(value: string): LedgerEntryId {
    if (!value || value.trim() === '') {
      throw new Error('LedgerEntryId cannot be empty');
    }
    return value as LedgerEntryId;
  },
  generate(): LedgerEntryId {
    return crypto.randomUUID() as LedgerEntryId;
  },
};

export const PaymentMethodId = {
  from(value: string): PaymentMethodId {
    if (!value || value.trim() === '') {
      throw new Error('PaymentMethodId cannot be empty');
    }
    return value as PaymentMethodId;
  },
  generate(): PaymentMethodId {
    return crypto.randomUUID() as PaymentMethodId;
  },
};

export const WebhookId = {
  from(value: string): WebhookId {
    if (!value || value.trim() === '') {
      throw new Error('WebhookId cannot be empty');
    }
    return value as WebhookId;
  },
  generate(): WebhookId {
    return crypto.randomUUID() as WebhookId;
  },
};

export const UserId = {
  from(value: string): UserId {
    if (!value || value.trim() === '') {
      throw new Error('UserId cannot be empty');
    }
    return value as UserId;
  },
  generate(): UserId {
    return crypto.randomUUID() as UserId;
  },
};

export const IdempotencyKey = {
  from(value: string): IdempotencyKey {
    if (!value || value.trim() === '') {
      throw new Error('IdempotencyKey cannot be empty');
    }
    return value as IdempotencyKey;
  },
};

export const ExternalReference = {
  from(value: string): ExternalReference {
    return value as ExternalReference;
  },
};

export const ApiTokenId = {
  from(value: string): ApiTokenId {
    if (!value || value.trim() === '') {
      throw new Error('ApiTokenId cannot be empty');
    }
    return value as ApiTokenId;
  },
  generate(): ApiTokenId {
    return crypto.randomUUID() as ApiTokenId;
  },
};
