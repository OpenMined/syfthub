import React, { useState } from 'react';

import type { Connection } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';
import Copy from 'lucide-react/dist/esm/icons/copy';
import Database from 'lucide-react/dist/esm/icons/database';
import Globe from 'lucide-react/dist/esm/icons/globe';
import HardDrive from 'lucide-react/dist/esm/icons/hard-drive';
import Link2 from 'lucide-react/dist/esm/icons/link-2';
import Radio from 'lucide-react/dist/esm/icons/radio';
import Wifi from 'lucide-react/dist/esm/icons/wifi';
import Zap from 'lucide-react/dist/esm/icons/zap';

import { cn } from '@/lib/utils';

import { Badge } from './ui/badge';
import { Button } from './ui/button';

// Connection type configuration with colors and icons
const CONNECTION_TYPE_CONFIG: Record<
  string,
  {
    icon: React.ElementType;
    label: string;
    color: string;
    bgColor: string;
    borderColor: string;
    dotColor: string;
  }
> = {
  rest_api: {
    icon: Globe,
    label: 'REST API',
    color: 'text-sky-600 dark:text-sky-400',
    bgColor: 'bg-sky-50 dark:bg-sky-950',
    borderColor: 'border-sky-200 dark:border-sky-800',
    dotColor: 'bg-sky-500 dark:bg-sky-400'
  },
  graphql: {
    icon: Radio,
    label: 'GraphQL',
    color: 'text-pink-600 dark:text-pink-400',
    bgColor: 'bg-pink-50 dark:bg-pink-950',
    borderColor: 'border-pink-200 dark:border-pink-800',
    dotColor: 'bg-pink-500 dark:bg-pink-400'
  },
  websocket: {
    icon: Wifi,
    label: 'WebSocket',
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-50 dark:bg-emerald-950',
    borderColor: 'border-emerald-200 dark:border-emerald-800',
    dotColor: 'bg-emerald-500 dark:bg-emerald-400'
  },
  grpc: {
    icon: Zap,
    label: 'gRPC',
    color: 'text-orange-600 dark:text-orange-400',
    bgColor: 'bg-orange-50 dark:bg-orange-950',
    borderColor: 'border-orange-200 dark:border-orange-800',
    dotColor: 'bg-orange-500 dark:bg-orange-400'
  },
  database: {
    icon: Database,
    label: 'Database',
    color: 'text-indigo-600 dark:text-indigo-400',
    bgColor: 'bg-indigo-50 dark:bg-indigo-950',
    borderColor: 'border-indigo-200 dark:border-indigo-800',
    dotColor: 'bg-indigo-500 dark:bg-indigo-400'
  },
  s3: {
    icon: HardDrive,
    label: 'S3 Storage',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-50 dark:bg-amber-950',
    borderColor: 'border-amber-200 dark:border-amber-800',
    dotColor: 'bg-amber-500 dark:bg-amber-400'
  },
  storage: {
    icon: HardDrive,
    label: 'Storage',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-50 dark:bg-amber-950',
    borderColor: 'border-amber-200 dark:border-amber-800',
    dotColor: 'bg-amber-500 dark:bg-amber-400'
  }
};

const DEFAULT_CONFIG = {
  icon: Link2,
  label: 'Connection',
  color: 'text-slate-600 dark:text-slate-400',
  bgColor: 'bg-slate-50 dark:bg-slate-950',
  borderColor: 'border-slate-200 dark:border-slate-800',
  dotColor: 'bg-slate-500 dark:bg-slate-400'
};

function getConnectionConfig(type: string) {
  return CONNECTION_TYPE_CONFIG[type.toLowerCase()] ?? DEFAULT_CONFIG;
}

interface SingleConnectionProperties {
  connection: Connection;
  isCompact?: boolean;
  endpointSlug?: string;
}

function SingleConnection({
  connection,
  isCompact = false,
  endpointSlug
}: Readonly<SingleConnectionProperties>) {
  const [copied, setCopied] = useState(false);
  const config = getConnectionConfig(connection.type);
  const Icon = config.icon;

  const handleCopySlug = () => {
    if (endpointSlug) {
      void navigator.clipboard.writeText(endpointSlug);
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2000);
    }
  };

  return (
    <div
      className={cn(
        'group relative rounded-lg border transition-colors transition-shadow duration-200',
        config.borderColor,
        config.bgColor,
        connection.enabled ? 'hover:shadow-md hover:shadow-black/5' : 'opacity-60 grayscale-[30%]',
        isCompact ? 'p-3' : 'p-4'
      )}
    >
      {/* Header row */}
      <div className='flex items-start justify-between gap-3'>
        <div className='flex items-center gap-2.5'>
          {/* Icon with colored background */}
          <div
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-md',
              config.bgColor,
              'ring-1 ring-inset',
              config.borderColor
            )}
          >
            <Icon className={cn('h-4 w-4', config.color)} />
          </div>

          <div className='min-w-0'>
            <div className='flex items-center gap-2'>
              <span className={cn('text-sm font-semibold', config.color)}>{config.label}</span>
              {/* Status indicator with pulse animation for enabled */}
              <span className='relative flex h-2 w-2'>
                {connection.enabled ? (
                  <span
                    className={cn(
                      'absolute inline-flex h-full w-full animate-ping rounded-full opacity-75',
                      config.dotColor
                    )}
                  />
                ) : null}
                <span
                  className={cn(
                    'relative inline-flex h-2 w-2 rounded-full',
                    connection.enabled ? config.dotColor : 'bg-syft-placeholder'
                  )}
                />
              </span>
            </div>
            {!isCompact && connection.description ? (
              <p className='font-inter text-muted-foreground mt-0.5 line-clamp-1 text-xs'>
                {connection.description}
              </p>
            ) : null}
          </div>
        </div>

        {/* Status badge */}
        <Badge
          variant='outline'
          className={cn(
            'shrink-0 text-[10px] font-medium',
            connection.enabled
              ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
              : 'border-border bg-muted text-muted-foreground'
          )}
        >
          {connection.enabled ? 'Active' : 'Disabled'}
        </Badge>
      </div>

      {/* Endpoint slug section */}
      {endpointSlug ? (
        <div className='mt-3'>
          <div className='flex items-center gap-2'>
            <code
              className={cn(
                'flex-1 truncate rounded-lg px-2.5 py-1.5 font-mono text-xs',
                'bg-card/80 text-muted-foreground ring-border ring-1 ring-inset',
                'group-hover:bg-card group-hover:ring-input transition-colors'
              )}
              title={endpointSlug}
            >
              {endpointSlug}
            </code>
            <Button
              variant='ghost'
              size='sm'
              onClick={handleCopySlug}
              className={cn(
                'h-7 w-7 shrink-0 p-0 transition-colors',
                copied
                  ? 'bg-emerald-100 text-emerald-600 hover:bg-emerald-100'
                  : 'text-syft-placeholder hover:bg-card hover:text-muted-foreground'
              )}
              title={copied ? 'Copied!' : 'Copy slug'}
            >
              {copied ? <Check className='h-3.5 w-3.5' /> : <Copy className='h-3.5 w-3.5' />}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

interface ConnectionCardProperties {
  connections: Connection[];
  title?: string;
  showEmpty?: boolean;
  endpointSlug?: string;
}

export function ConnectionCard({
  connections,
  title = 'Connections',
  showEmpty = true,
  endpointSlug
}: Readonly<ConnectionCardProperties>) {
  // Filter to only show connections (optionally filter to enabled only)
  const validConnections = connections.filter((c) => c.type);

  if (validConnections.length === 0 && !showEmpty) {
    return null;
  }

  return (
    <div className='border-border bg-card rounded-xl border p-6'>
      {/* Header */}
      <div className='mb-4 flex items-center justify-between'>
        <h3 className='font-rubik text-foreground text-sm font-medium'>{title}</h3>
        {validConnections.length > 0 ? (
          <span className='bg-accent text-muted-foreground rounded-full px-2 py-0.5 text-xs font-medium'>
            {validConnections.length}
          </span>
        ) : null}
      </div>

      {/* Connections list */}
      {validConnections.length > 0 ? (
        <div className='space-y-3'>
          {validConnections.map((connection, index) => (
            <SingleConnection
              key={`${connection.type}-${String(index)}`}
              connection={connection}
              isCompact={validConnections.length > 2}
              endpointSlug={endpointSlug}
            />
          ))}
        </div>
      ) : (
        <div className='border-border rounded-xl border border-dashed py-6 text-center'>
          <Link2 className='text-syft-placeholder mx-auto h-8 w-8' />
          <p className='font-inter text-muted-foreground mt-2 text-sm'>No connections configured</p>
          <p className='font-inter text-syft-placeholder mt-1 text-xs'>
            Add a connection to enable external access to this endpoint
          </p>
        </div>
      )}
    </div>
  );
}

// Export for use in other components
export { SingleConnection, getConnectionConfig, CONNECTION_TYPE_CONFIG };
