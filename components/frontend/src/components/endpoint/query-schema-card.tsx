import { memo, useState } from 'react';

import type { EndpointType, QuerySchema } from '@/lib/types';

import { Filter, Info } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

export interface QuerySchemaCardProperties {
  schema?: QuerySchema | null;
  endpointType: EndpointType;
}

// Badges shown before the reader asks for the rest.
const VISIBLE = 5;

function describe(schema: QuerySchema, filterableCount: number): string {
  const returned = 'Every result carries these metadata fields alongside its content.';
  if (!schema.filters) return returned;
  if (filterableCount === 0) {
    return `${returned} The owner has not enabled filtering on any of them.`;
  }
  return `${returned} Highlighted fields accept query filters, so a search can be narrowed to a date range, an author, a set of tags and so on.`;
}

// What a query may carry, as the publisher declared it. Rendered only for sources
// that return documents and whose space published at least one metadata field.
export const QuerySchemaCard = memo(function QuerySchemaCard({
  schema,
  endpointType
}: Readonly<QuerySchemaCardProperties>) {
  const [expanded, setExpanded] = useState(false);
  if (!schema || endpointType === 'model' || schema.metadata_fields.length === 0) return null;

  const fields = schema.metadata_fields.toSorted((a, b) => a.localeCompare(b));
  const filterable = schema.filters?.fields ?? {};
  const filterableCount = Object.keys(filterable).length;
  const shown = expanded ? fields : fields.slice(0, VISIBLE);
  const hidden = fields.length - shown.length;

  return (
    <div className='border-border bg-card rounded-xl border p-6'>
      <div className='mb-3 flex items-center justify-between gap-2'>
        <div className='flex items-center gap-1.5'>
          <h3 className='font-rubik text-foreground text-sm font-medium'>Metadata</h3>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type='button'
                  aria-label='About metadata'
                  className='text-muted-foreground hover:text-foreground'
                >
                  <Info className='size-3.5' />
                </button>
              </TooltipTrigger>
              <TooltipContent side='top' className='max-w-64'>
                {describe(schema, filterableCount)}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        {schema.filters ? (
          <span className='font-inter text-muted-foreground text-xs'>
            {filterableCount} of {fields.length} filterable
          </span>
        ) : null}
      </div>
      <div className='flex flex-wrap gap-1'>
        {shown.map((name) => {
          const spec = filterable[name];
          return spec ? (
            <Badge key={name} variant='secondary' className='gap-1 font-mono' title={spec.type}>
              <Filter className='size-3' aria-label='filterable' />
              {name}
            </Badge>
          ) : (
            <Badge key={name} variant='outline' className='font-mono'>
              {name}
            </Badge>
          );
        })}
        {hidden > 0 || expanded ? (
          <button
            type='button'
            onClick={() => {
              setExpanded((open) => !open);
            }}
            className='font-inter text-muted-foreground hover:text-foreground px-1 text-xs'
          >
            {expanded ? 'Show less' : `+${String(hidden)} more`}
          </button>
        ) : null}
      </div>
    </div>
  );
});
