/**
 * Violet-themed bundle dropdown shared by the Xendit-policy sidebar card
 * and the chat-flow subscription gate modal.
 */
import type { MoneyBundle } from '@/lib/xendit-client';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { formatRequestEstimate } from '@/lib/xendit-client';

export interface BundlePickerProperties {
  bundles: MoneyBundle[];
  currency: string;
  value: string;
  onChange: (name: string) => void;
  disabled?: boolean;
  triggerClassName?: string;
  /** When set (>0), each option shows an estimated request count. */
  pricePerRequest?: number | null;
}

function RequestEstimate({
  amount,
  pricePerRequest
}: Readonly<{ amount: number; pricePerRequest: number }>) {
  return (
    <>
      <span className='opacity-40' aria-hidden='true'>
        ·
      </span>
      <span className='text-[11px] font-normal opacity-75'>
        {formatRequestEstimate(amount, pricePerRequest)}
      </span>
    </>
  );
}

export function BundlePicker({
  bundles,
  currency,
  value,
  onChange,
  disabled,
  triggerClassName,
  pricePerRequest
}: Readonly<BundlePickerProperties>) {
  const selected = bundles.find((b) => b.name === value) ?? bundles[0];
  if (!selected) return null;

  const showRequestEstimate = typeof pricePerRequest === 'number' && pricePerRequest > 0;

  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger
        className={cn(
          'h-10 text-sm transition-colors',
          'border-border bg-background text-foreground',
          'hover:border-input hover:bg-muted/40',
          'focus:ring-violet-400/40 dark:focus:ring-violet-500/30',
          triggerClassName
        )}
      >
        <SelectValue>
          <span className='flex w-full items-center gap-2 pr-1'>
            <span className='font-medium tabular-nums'>
              {currency} {selected.amount.toLocaleString()}
            </span>
            {showRequestEstimate && (
              <RequestEstimate amount={selected.amount} pricePerRequest={pricePerRequest} />
            )}
          </span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {bundles.map((bundle) => (
          <SelectItem key={bundle.name} value={bundle.name} className='text-sm'>
            <span className='flex items-center gap-2'>
              <span className='font-medium tabular-nums'>
                {currency} {bundle.amount.toLocaleString()}
              </span>
              {showRequestEstimate && (
                <RequestEstimate amount={bundle.amount} pricePerRequest={pricePerRequest} />
              )}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
