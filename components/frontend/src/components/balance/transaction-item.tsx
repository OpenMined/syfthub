import type { AccountingTransaction } from '@/lib/types';

import ArrowDownLeft from 'lucide-react/dist/esm/icons/arrow-down-left';
import ArrowUpRight from 'lucide-react/dist/esm/icons/arrow-up-right';

import { cn } from '@/lib/utils';

import { formatBalance } from './balance-display';

/**
 * Format relative time for transactions.
 */
function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${String(diffMins)}m ago`;
  if (diffHours < 24) return `${String(diffHours)}h ago`;
  if (diffDays < 7) return `${String(diffDays)}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Truncate email for display.
 */
function truncateEmail(email: string | null | undefined, maxLength = 20): string {
  if (!email) return 'Unknown';
  if (email.length <= maxLength) return email;
  const atIndex = email.indexOf('@');
  if (atIndex === -1) return email.slice(0, maxLength) + '…';
  const local = email.slice(0, atIndex);
  const domain = email.slice(atIndex + 1);
  const availableLocal = maxLength - domain.length - 4; // 4 for "…@"
  if (availableLocal < 3) return email.slice(0, maxLength) + '…';
  return `${local.slice(0, availableLocal)}…@${domain}`;
}

export interface TransactionItemProps {
  /** The transaction to display */
  transaction: AccountingTransaction;
  /** The current user's email, used to determine direction */
  userEmail: string | undefined;
}

/**
 * TransactionItem - Renders a single transaction row with
 * direction icon, party info, timestamp, and amount.
 */
export function TransactionItem({ transaction, userEmail }: Readonly<TransactionItemProps>) {
  const isIncoming = transaction.recipientEmail === userEmail;
  const otherParty = isIncoming ? transaction.senderEmail : transaction.recipientEmail;

  return (
    <div className='flex items-center gap-3'>
      <div
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded-full',
          isIncoming ? 'bg-emerald-100' : 'bg-red-100'
        )}
      >
        {isIncoming ? (
          <ArrowDownLeft className='h-3 w-3 text-emerald-600' />
        ) : (
          <ArrowUpRight className='h-3 w-3 text-red-600' />
        )}
      </div>
      <div className='min-w-0 flex-1'>
        <div className='text-foreground truncate text-xs font-medium'>
          {isIncoming ? 'From ' : 'To '}
          {truncateEmail(otherParty)}
        </div>
        <div className='text-muted-foreground text-[10px]'>
          {formatRelativeTime(transaction.createdAt)}
        </div>
      </div>
      <div className={cn('text-xs font-medium', isIncoming ? 'text-emerald-600' : 'text-red-600')}>
        {isIncoming ? '+' : '-'}
        {formatBalance(transaction.amount)}
      </div>
    </div>
  );
}
