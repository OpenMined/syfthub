import { memo } from 'react';

import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';

export interface ResourceLinkProps {
  label: string;
  href: string;
}

// Memoized ResourceLink component
export const ResourceLink = memo(function ResourceLink({
  label,
  href
}: Readonly<ResourceLinkProps>) {
  return (
    <a
      href={href}
      target='_blank'
      rel='noopener noreferrer'
      className='text-muted-foreground hover:bg-muted hover:text-foreground flex items-center justify-between rounded p-2 text-sm transition-colors'
    >
      {label}
      <ArrowRight className='h-4 w-4 opacity-50' />
    </a>
  );
});
