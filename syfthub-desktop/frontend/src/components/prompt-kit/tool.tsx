import { useState } from 'react';

import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';
import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Settings from 'lucide-react/dist/esm/icons/settings';
import XCircle from 'lucide-react/dist/esm/icons/x-circle';

import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';

export type ToolState =
  | 'input-streaming'
  | 'input-available'
  | 'output-available'
  | 'output-error';

export type ToolPart = {
  type: string;
  state: ToolState;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  toolCallId?: string;
  errorText?: string;
};

export type ToolProps = {
  toolPart: ToolPart;
  defaultOpen?: boolean;
  className?: string;
};

const Tool = ({ toolPart, defaultOpen = false, className }: ToolProps) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  const { state, input, output, toolCallId } = toolPart;

  // Icon + badge palettes are bound to semantic theme tokens (primary,
  // success, destructive, muted) so they shift with the active theme and
  // never drift away from the OpenMined teal palette. Earlier versions used
  // raw Tailwind colors (blue-500, orange-500, ...) which broke both light
  // mode and palette cohesion.
  const getStateIcon = () => {
    switch (state) {
      case 'input-streaming':
        return <Loader2 className='text-primary h-4 w-4 animate-spin' aria-hidden='true' />;
      case 'input-available':
        return <Settings className='text-muted-foreground h-4 w-4' aria-hidden='true' />;
      case 'output-available':
        return <CheckCircle className='text-success h-4 w-4' aria-hidden='true' />;
      case 'output-error':
        return <XCircle className='text-destructive h-4 w-4' aria-hidden='true' />;
      default:
        return <Settings className='text-muted-foreground h-4 w-4' aria-hidden='true' />;
    }
  };

  const getStateBadge = () => {
    const baseClasses = 'rounded px-1.5 py-0.5 text-[10px] font-medium tracking-wide uppercase';
    switch (state) {
      case 'input-streaming':
        return (
          <span className={cn(baseClasses, 'bg-primary/10 text-primary')}>
            Running
          </span>
        );
      case 'input-available':
        return (
          <span className={cn(baseClasses, 'bg-muted text-muted-foreground')}>
            Queued
          </span>
        );
      case 'output-available':
        return (
          <span className={cn(baseClasses, 'bg-success/10 text-success')}>
            Done
          </span>
        );
      case 'output-error':
        return (
          <span className={cn(baseClasses, 'bg-destructive/10 text-destructive')}>
            Error
          </span>
        );
      default:
        return (
          <span className={cn(baseClasses, 'bg-muted text-muted-foreground')}>
            Pending
          </span>
        );
    }
  };

  const formatValue = (value: unknown): string => {
    if (value === null) return 'null';
    if (value === undefined) return 'undefined';
    if (typeof value === 'string') return value;
    if (typeof value === 'object') {
      return JSON.stringify(value, null, 2);
    }
    return String(value);
  };

  return (
    <div
      className={cn(
        'border-border bg-card mt-3 overflow-hidden rounded-lg border',
        className
      )}
    >
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <Button
            variant='ghost'
            aria-expanded={isOpen}
            className='hover:bg-muted/60 h-auto w-full justify-between rounded-b-none px-3 py-2 font-normal'
          >
            <div className='flex items-center gap-2'>
              {getStateIcon()}
              <span className='text-foreground font-mono text-sm font-medium'>
                {toolPart.type}
              </span>
              {getStateBadge()}
            </div>
            <ChevronDown
              className={cn(
                'text-muted-foreground h-4 w-4 transition-transform duration-150',
                isOpen && 'rotate-180'
              )}
              aria-hidden='true'
            />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent
          className={cn(
            'border-border border-t',
            'data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down overflow-hidden'
          )}
        >
          <div className='bg-card space-y-3 p-3'>
            {input && Object.keys(input).length > 0 && (
              <div>
                <h4 className='text-muted-foreground mb-2 text-[11px] font-medium uppercase tracking-wide'>
                  Input
                </h4>
                <div className='bg-muted/50 border-border rounded-md border p-2 font-mono text-[13px]'>
                  {Object.entries(input).map(([key, value]) => (
                    <div key={key} className='mb-1 last:mb-0'>
                      <span className='text-muted-foreground'>{key}:</span>{' '}
                      <span className='text-foreground'>{formatValue(value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {output && (
              <div>
                <h4 className='text-muted-foreground mb-2 text-[11px] font-medium uppercase tracking-wide'>
                  Output
                </h4>
                <div className='bg-muted/50 border-border max-h-60 overflow-auto rounded-md border p-2 font-mono text-[13px]'>
                  <pre className='text-foreground whitespace-pre-wrap'>
                    {formatValue(output)}
                  </pre>
                </div>
              </div>
            )}

            {state === 'output-error' && toolPart.errorText && (
              <div>
                <h4 className='text-destructive mb-2 text-[11px] font-medium uppercase tracking-wide'>
                  Error
                </h4>
                <div className='bg-destructive/10 border-destructive/30 text-destructive rounded-md border p-2 text-sm'>
                  {toolPart.errorText}
                </div>
              </div>
            )}

            {state === 'input-streaming' && (
              <div className='text-muted-foreground text-sm'>
                Processing tool call…
              </div>
            )}

            {toolCallId && (
              <div className='text-muted-foreground border-border border-t pt-2 text-[11px]'>
                <span className='font-mono'>Call ID: {toolCallId}</span>
              </div>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
};

export { Tool };
