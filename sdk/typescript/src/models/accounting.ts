/**
 * Account balance information.
 */
export interface AccountingBalance {
  readonly credits: number;
  readonly currency: string;
  readonly updatedAt: Date | null;
}

/**
 * Transaction types.
 */
export const TransactionType = {
  CREDIT: 'credit',
  DEBIT: 'debit',
  REFUND: 'refund',
} as const;

export type TransactionType = (typeof TransactionType)[keyof typeof TransactionType];

/**
 * Account transaction record.
 */
export interface AccountingTransaction {
  readonly id: string;
  readonly amount: number;
  readonly description: string;
  readonly transactionType: TransactionType;
  readonly createdAt: Date;
}
