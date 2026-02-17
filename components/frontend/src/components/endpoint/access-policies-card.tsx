import { memo } from 'react';

import type { Policy } from '@/lib/types';

import Unlock from 'lucide-react/dist/esm/icons/unlock';

import { PolicyItem } from './policy-item';

export interface AccessPoliciesCardProperties {
  policies?: Policy[];
}

// Access Policies Card component - memoized to prevent unnecessary re-renders
export const AccessPoliciesCard = memo(function AccessPoliciesCard({
  policies
}: Readonly<AccessPoliciesCardProperties>) {
  const validPolicies = policies?.filter((p) => p.type) ?? [];

  return (
    <div className='border-border bg-card rounded-xl border p-6'>
      {/* Header */}
      <div className='mb-4 flex items-center justify-between'>
        <h3 className='font-rubik text-foreground text-sm font-medium'>Access Policies</h3>
        {validPolicies.length > 0 ? (
          <span className='bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs font-medium'>
            {validPolicies.length}
          </span>
        ) : null}
      </div>

      {/* Policies list */}
      {validPolicies.length > 0 ? (
        <div className='space-y-3'>
          {validPolicies.map((policy, index) => (
            <PolicyItem key={`${policy.type}-${String(index)}`} policy={policy} />
          ))}
        </div>
      ) : (
        <div className='border-border rounded-xl border border-dashed py-6 text-center'>
          <Unlock className='text-muted-foreground mx-auto h-8 w-8' />
          <p className='font-inter text-muted-foreground mt-2 text-sm'>
            No access policies configured
          </p>
          <p className='font-inter text-muted-foreground mt-1 text-xs'>
            This endpoint may be publicly accessible
          </p>
        </div>
      )}
    </div>
  );
});
