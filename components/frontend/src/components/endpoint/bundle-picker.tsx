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

export interface BundlePickerProperties {
  bundles: MoneyBundle[];
  currency: string;
  value: string;
  onChange: (name: string) => void;
  disabled?: boolean;
  triggerClassName?: string;
}

export function BundlePicker({
  bundles,
  currency,
  value,
  onChange,
  disabled,
  triggerClassName
}: Readonly<BundlePickerProperties>) {
  const selected = bundles.find((b) => b.name === value) ?? bundles[0];
  if (!selected) return null;

  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger
        className={cn(
          'h-8 text-xs transition-colors',
          'border-violet-300 bg-violet-50 text-violet-700',
          'hover:bg-violet-100 focus:ring-violet-400/40',
          'dark:border-violet-700 dark:bg-violet-950/30 dark:text-violet-300',
          'dark:hover:bg-violet-900/40 dark:focus:ring-violet-500/30',
          triggerClassName
        )}
      >
        <SelectValue>
          <span className='flex w-full items-center pr-1'>
            <span className='font-medium tabular-nums'>
              {currency} {selected.amount.toLocaleString()}
            </span>
          </span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent
        className={cn(
          'border-violet-200 bg-violet-50/95 backdrop-blur-sm',
          'dark:border-violet-800 dark:bg-violet-950/95'
        )}
      >
        {bundles.map((bundle) => (
          <SelectItem
            key={bundle.name}
            value={bundle.name}
            className={cn(
              'text-xs text-violet-800 focus:bg-violet-100 focus:text-violet-900',
              'dark:text-violet-200 dark:focus:bg-violet-900/50 dark:focus:text-violet-100'
            )}
          >
            <span className='font-medium tabular-nums'>
              {currency} {bundle.amount.toLocaleString()}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
