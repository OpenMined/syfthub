import type { AccountingTransaction } from '@/lib/types';

import { TransactionItem } from './transaction-item';

export interface TransactionListProps {
  /** Whether transaction data is still loading */
  isLoading: boolean;
  /** List of transactions to display */
  transactions: AccountingTransaction[];
  /** The current user's email, used by TransactionItem to determine direction */
  userEmail: string | undefined;
}

/**
 * TransactionList - Renders a list of transactions with loading
 * skeletons and empty state handling.
 */
export function TransactionList({
  isLoading,
  transactions,
  userEmail
}: Readonly<TransactionListProps>) {
  if (isLoading) {
    return (
      <div className='space-y-2'>
        {[0, 1, 2].map((index) => (
          <div key={index} className='flex animate-pulse items-center gap-3'>
            <div className='bg-muted h-6 w-6 rounded-full' />
            <div className='flex-1'>
              <div className='bg-muted h-3 w-24 rounded' />
              <div className='bg-muted mt-1 h-2 w-16 rounded' />
            </div>
            <div className='bg-muted h-3 w-12 rounded' />
          </div>
        ))}
      </div>
    );
  }

  if (transactions.length === 0) {
    return (
      <div className='text-muted-foreground py-4 text-center text-xs'>No recent transactions</div>
    );
  }

  return (
    <div className='space-y-2'>
      {transactions.map((tx) => (
        <TransactionItem key={tx.id} transaction={tx} userEmail={userEmail} />
      ))}
    </div>
  );
}
