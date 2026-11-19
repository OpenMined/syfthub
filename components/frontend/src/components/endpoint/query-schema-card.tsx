import { memo } from 'react';

import type { EndpointType, QuerySchema } from '@/lib/types';

import { Badge } from '@/components/ui/badge';

export interface QuerySchemaCardProperties {
  schema?: QuerySchema | null;
  endpointType: EndpointType;
}

// What a query may carry, as the publisher declared it. Rendered only for sources
// that return documents and whose space published a schema.
export const QuerySchemaCard = memo(function QuerySchemaCard({
  schema,
  endpointType
}: Readonly<QuerySchemaCardProperties>) {
  if (!schema || endpointType === 'model') return null;
  const returned = schema.metadata_fields;
  const filters = schema.filters;
  const filterable = filters ? Object.entries(filters.fields) : [];

  return (
    <div className='border-border bg-card rounded-xl border p-6'>
      <h3 className='font-rubik text-foreground mb-4 text-sm font-medium'>Metadata</h3>
      <div className='space-y-4'>
        <div>
          <p className='font-inter text-muted-foreground mb-1 text-xs'>Returned with results</p>
          {returned.length > 0 ? (
            <div className='flex flex-wrap gap-1'>
              {returned.map((name) => (
                <Badge key={name} variant='outline' className='font-mono'>
                  {name}
                </Badge>
              ))}
            </div>
          ) : (
            <p className='font-inter text-muted-foreground text-sm'>None</p>
          )}
        </div>

        {filters ? (
          <div>
            <p className='font-inter text-muted-foreground mb-1 text-xs'>Filterable</p>
            {filterable.length > 0 ? (
              <ul className='space-y-1'>
                {filterable.map(([name, spec]) => (
                  <li key={name} className='flex items-center justify-between gap-2 text-sm'>
                    <span className='text-foreground font-mono'>{name}</span>
                    <span className='font-inter text-muted-foreground text-xs'>{spec.type}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className='font-inter text-muted-foreground text-sm'>
                Queries cannot filter this source
              </p>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
});
