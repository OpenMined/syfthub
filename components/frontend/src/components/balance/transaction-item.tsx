import type { WalletTransaction } from '@/lib/types';

import ArrowDownLeft from 'lucide-react/dist/esm/icons/arrow-down-left';
import ArrowUpRight from 'lucide-react/dist/esm/icons/arrow-up-right';

import { cn } from '@/lib/utils';

import { formatBalance } from './balance-display';

/**
 * Format relative time for transactions.
 */
function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
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
 * Truncate an identifier (email or wallet address) for display.
 */
function truncateIdentifier(value: string | null | undefined, maxLength = 20): string {
  if (!value) return 'Unknown';

  // Wallet address: show 0xABCD...1234
  if (value.startsWith('0x') && value.length > 12) {
    return `${value.slice(0, 6)}...${value.slice(-4)}`;
  }

  // Email: truncate local part
  if (value.length <= maxLength) return value;
  const atIndex = value.indexOf('@');
  if (atIndex === -1) return value.slice(0, maxLength) + '...';
  const local = value.slice(0, atIndex);
  const domain = value.slice(atIndex + 1);
  const availableLocal = maxLength - domain.length - 4; // 4 for "...@"
  if (availableLocal < 3) return value.slice(0, maxLength) + '...';
  return `${local.slice(0, availableLocal)}...@${domain}`;
}

export interface TransactionItemProps {
  /** The transaction to display */
  transaction: WalletTransaction;
  /** The current user's email, used to determine direction */
  userEmail?: string;
  /** The current user's wallet address, used to determine direction */
  walletAddress?: string;
}

/**
 * TransactionItem - Renders a single transaction row with
 * direction icon, party info, timestamp, and amount.
 */
export function TransactionItem({ transaction, userEmail, walletAddress }: Readonly<TransactionItemProps>) {
  const isIncoming =
    (userEmail ? transaction.recipient_email === userEmail : false) ||
    (walletAddress ? transaction.recipient_email.toLowerCase() === walletAddress.toLowerCase() : false);
  const otherParty = isIncoming ? transaction.sender_email : transaction.recipient_email;

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
          {truncateIdentifier(otherParty)}
        </div>
        <div className='text-muted-foreground text-[10px]'>
          {formatRelativeTime(transaction.created_at)}
        </div>
      </div>
      <div className={cn('text-xs font-medium', isIncoming ? 'text-emerald-600' : 'text-red-600')}>
        {isIncoming ? '+' : '-'}
        {formatBalance(transaction.amount)}
      </div>
    </div>
  );
}
