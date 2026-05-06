import type { EndpointType } from '@/lib/types';

import Database from 'lucide-react/dist/esm/icons/database';
import Sparkles from 'lucide-react/dist/esm/icons/sparkles';

import {
  getEndpointTypeIcon,
  getEndpointTypeIconColor,
  getEndpointTypeLabel
} from '@/lib/endpoint-utils';

interface EndpointTypeIconProps {
  type: EndpointType;
  /** Size class — defaults to "h-4 w-4". Pass e.g. "h-3.5 w-3.5" for compound branch parity. */
  className?: string;
}

export function EndpointTypeIcon({ type, className = 'h-4 w-4' }: Readonly<EndpointTypeIconProps>) {
  if (type === 'model_data_source') {
    return (
      <span className='flex shrink-0 items-center gap-0.5' aria-label='Model and Data Source'>
        <Sparkles className='h-3.5 w-3.5 text-purple-500' />
        <Database className='h-3.5 w-3.5 text-emerald-500' />
      </span>
    );
  }

  const Icon = getEndpointTypeIcon(type);
  const colorClass = getEndpointTypeIconColor(type);
  return (
    <Icon
      className={`${className} shrink-0 ${colorClass}`}
      aria-label={getEndpointTypeLabel(type)}
    />
  );
}
