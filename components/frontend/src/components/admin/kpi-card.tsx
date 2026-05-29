import type { LucideIcon } from 'lucide-react';
import type React from 'react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface KpiCardProperties {
  /** Short label, e.g. "Total Users". */
  label: string;
  /** The headline value. Strings render verbatim; numbers are grouped. */
  value: number | string;
  icon?: LucideIcon;
  /** Optional supporting line under the value. */
  hint?: React.ReactNode;
  /** Optional emphasized delta / secondary metric (e.g. "92% verified"). */
  delta?: React.ReactNode;
  /** Tone for the delta text. */
  deltaTone?: 'positive' | 'negative' | 'muted';
  className?: string;
}

/** Format a number with locale grouping; pass strings through untouched. */
function formatValue(value: number | string): string {
  return typeof value === 'number' ? value.toLocaleString() : value;
}

const deltaToneClass: Record<NonNullable<KpiCardProperties['deltaTone']>, string> = {
  positive: 'text-primary',
  negative: 'text-destructive',
  muted: 'text-muted-foreground'
};

/**
 * A single headline metric tile. Uses tabular numerals so values line up across
 * the KPI grid and reuses the shared Card primitive + brand tokens.
 */
export function KpiCard({
  label,
  value,
  icon: Icon,
  hint,
  delta,
  deltaTone = 'muted',
  className
}: Readonly<KpiCardProperties>) {
  return (
    <Card className={cn('border-border/50 gap-3 py-5', className)}>
      <CardHeader className='gap-1.5'>
        <CardTitle className='text-muted-foreground flex items-center gap-2 text-sm font-medium'>
          {Icon ? <Icon className='size-4' aria-hidden='true' /> : null}
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className='flex flex-col gap-1'>
        <span className='text-foreground text-3xl font-semibold tabular-nums'>
          {formatValue(value)}
        </span>
        {delta ? (
          <span className={cn('text-sm font-medium tabular-nums', deltaToneClass[deltaTone])}>
            {delta}
          </span>
        ) : null}
        {hint ? <span className='text-muted-foreground text-xs'>{hint}</span> : null}
      </CardContent>
    </Card>
  );
}
