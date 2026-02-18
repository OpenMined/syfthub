import { useCallback, useState } from 'react';

import type { ChatSource, EndpointGroup } from '@/lib/types';

import ChevronRight from 'lucide-react/dist/esm/icons/chevron-right';
import Cpu from 'lucide-react/dist/esm/icons/cpu';
import Database from 'lucide-react/dist/esm/icons/database';
import Folder from 'lucide-react/dist/esm/icons/folder';
import FolderOpen from 'lucide-react/dist/esm/icons/folder-open';
import MoreHorizontal from 'lucide-react/dist/esm/icons/more-horizontal';
import { Link } from 'react-router-dom';

// =============================================================================
// Types
// =============================================================================

interface GlobalDirectoryProps {
  /** Endpoint groups from the grouped API (preferred) */
  groups?: EndpointGroup[];
  /** Loading state */
  isLoading: boolean;
}

// =============================================================================
// Constants
// =============================================================================

const NODE_COLORS = ['#6976ae', '#53bea9', '#937098', '#52a8c5', '#f79763', '#cc677b'] as const;

function getNodeColor(index: number): string {
  return NODE_COLORS[index % NODE_COLORS.length] as string;
}

// =============================================================================
// Sub-components
// =============================================================================

function DirectoryEntry({
  endpoint,
  depth,
  colorIndex
}: Readonly<{
  endpoint: ChatSource;
  depth: number;
  colorIndex: number;
}>) {
  const color = getNodeColor(colorIndex);
  const href = endpoint.owner_username ? `/${endpoint.owner_username}/${endpoint.slug}` : '/browse';

  const isModel = endpoint.type === 'model' || endpoint.type === 'model_data_source';
  const Icon = isModel ? Cpu : Database;

  return (
    <Link
      to={href}
      title={endpoint.description || endpoint.name}
      className='group flex items-center gap-2 rounded-md px-2 py-1 transition-colors hover:bg-[var(--accent)]'
      style={{ paddingLeft: `${String(depth * 18 + 8)}px` }}
    >
      {/* Tree connector line */}
      <span className='text-muted-foreground/40 font-mono text-xs select-none' aria-hidden='true'>
        {depth > 0 ? '├─' : ''}
      </span>

      {/* File icon */}
      <Icon
        className='h-3.5 w-3.5 flex-shrink-0 transition-colors'
        style={{ color }}
        aria-hidden='true'
      />

      {/* Name */}
      <span className='text-foreground/80 group-hover:text-foreground flex-1 truncate font-mono text-xs tracking-tight transition-colors'>
        {endpoint.slug}
      </span>

      {/* Type badge */}
      <span
        className='rounded-sm px-1.5 py-0.5 font-mono text-[10px] tracking-wider uppercase opacity-50 transition-opacity group-hover:opacity-80'
        style={{ color, backgroundColor: `${color}15` }}
      >
        {isModel ? 'model' : 'data'}
      </span>
    </Link>
  );
}

/**
 * "More" indicator when a folder has more endpoints than displayed.
 */
function MoreIndicator({
  owner,
  remainingCount,
  depth,
  colorIndex
}: Readonly<{
  owner: string;
  remainingCount: number;
  depth: number;
  colorIndex: number;
}>) {
  const color = getNodeColor(colorIndex);

  return (
    <Link
      to='/browse'
      title='View all endpoints'
      className='group flex items-center gap-2 rounded-md px-2 py-1 transition-colors hover:bg-[var(--accent)]'
      style={{ paddingLeft: `${String(depth * 18 + 8)}px` }}
    >
      {/* Tree connector line */}
      <span className='text-muted-foreground/40 font-mono text-xs select-none' aria-hidden='true'>
        └─
      </span>

      {/* More icon */}
      <MoreHorizontal
        className='h-3.5 w-3.5 flex-shrink-0 transition-colors'
        style={{ color }}
        aria-hidden='true'
      />

      {/* Label */}
      <span className='text-muted-foreground group-hover:text-foreground flex-1 truncate font-mono text-xs tracking-tight transition-colors'>
        +{remainingCount} more...
      </span>
    </Link>
  );
}

function FolderNode({
  group,
  colorIndex,
  defaultOpen
}: Readonly<{
  group: EndpointGroup;
  colorIndex: number;
  defaultOpen: boolean;
}>) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const color = getNodeColor(colorIndex);

  const toggle = useCallback(() => {
    setIsOpen((previous) => !previous);
  }, []);

  // Calculate remaining count for "more" indicator
  const displayedCount = group.endpoints.length;
  const remainingCount = group.total_count - displayedCount;

  return (
    <div>
      {/* Folder header */}
      <button
        type='button'
        onClick={toggle}
        className='group flex w-full items-center gap-2 rounded-md px-2 py-1 transition-colors hover:bg-[var(--accent)]'
      >
        {/* Chevron */}
        <ChevronRight
          className={`text-muted-foreground h-3 w-3 flex-shrink-0 transition-transform duration-200 ${
            isOpen ? 'rotate-90' : ''
          }`}
          aria-hidden='true'
        />

        {/* Folder icon */}
        {isOpen ? (
          <FolderOpen className='h-3.5 w-3.5 flex-shrink-0' style={{ color }} aria-hidden='true' />
        ) : (
          <Folder className='h-3.5 w-3.5 flex-shrink-0' style={{ color }} aria-hidden='true' />
        )}

        {/* Owner name */}
        <span className='text-foreground group-hover:text-foreground flex-1 truncate text-left font-mono text-xs font-medium tracking-tight'>
          {group.owner_username}/
        </span>

        {/* Count - show total_count, not just displayed count */}
        <span className='text-muted-foreground font-mono text-[10px] tabular-nums'>
          {group.total_count} {group.total_count === 1 ? 'node' : 'nodes'}
          {group.has_more && <span className='text-muted-foreground/50 ml-1'>...</span>}
        </span>
      </button>

      {/* Children */}
      {isOpen && (
        <div className='relative'>
          {/* Vertical tree line */}
          <div
            className='absolute top-0 bottom-0 left-[18px] w-px'
            style={{ backgroundColor: `${color}25` }}
            aria-hidden='true'
          />
          {group.endpoints.map((endpoint, index) => (
            <DirectoryEntry
              key={endpoint.id}
              endpoint={endpoint}
              depth={1}
              colorIndex={colorIndex + index}
            />
          ))}
          {/* Show "more" indicator if there are additional endpoints not displayed */}
          {group.has_more && (
            <MoreIndicator
              owner={group.owner_username}
              remainingCount={remainingCount}
              depth={1}
              colorIndex={colorIndex + displayedCount}
            />
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Loading skeleton
// =============================================================================

function DirectorySkeleton() {
  return (
    <div className='space-y-1'>
      {[0, 1, 2, 3, 4].map((index) => (
        <div key={index} className='flex animate-pulse items-center gap-2 px-2 py-1'>
          <div className='bg-muted h-3 w-3 rounded-sm' />
          <div className='bg-muted h-3.5 w-3.5 rounded-sm' />
          <div className='bg-muted h-3 flex-1 rounded-sm' />
          <div className='bg-muted h-3 w-8 rounded-sm' />
        </div>
      ))}
    </div>
  );
}

// =============================================================================
// Main component
// =============================================================================

export function GlobalDirectory({ groups, isLoading }: Readonly<GlobalDirectoryProps>) {
  // Calculate totals from groups
  const totalEndpoints = groups?.reduce((sum, g) => sum + g.total_count, 0) ?? 0;
  const totalContributors = groups?.length ?? 0;

  // Show nothing if no groups (empty state)
  if (!isLoading && (!groups || groups.length === 0)) {
    return null;
  }

  return (
    <div className='flex h-full min-h-0 flex-col'>
      {/* Section header */}
      <div className='mb-3 flex flex-shrink-0 items-center justify-between'>
        <div className='flex items-center gap-2'>
          <div className='h-5 w-1 rounded-full bg-gradient-to-b from-[#53bea9] via-[#6976ae] to-[#937098]'></div>
          <h4 className='font-rubik text-foreground text-xs tracking-wide uppercase'>
            Global Directory
          </h4>
          <span className='text-muted-foreground/50 font-mono text-[10px] tracking-wider'>
            / collective intelligence
          </span>
        </div>
      </div>

      {/* Directory tree */}
      <div className='bg-background/80 border-border/30 flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border'>
        {/* Terminal-style header bar */}
        <div className='border-border/30 flex flex-shrink-0 items-center gap-2 border-b px-3 py-1.5'>
          <div className='flex gap-1.5'>
            <div className='h-2 w-2 rounded-full bg-[#ff5f57]/60' />
            <div className='h-2 w-2 rounded-full bg-[#febc2e]/60' />
            <div className='h-2 w-2 rounded-full bg-[#28c840]/60' />
          </div>
          <span className='text-muted-foreground/50 font-mono text-[10px] tracking-wider'>
            ~/syft/network
          </span>
          <div className='flex-1' />
          <span className='text-muted-foreground/40 font-mono text-[10px] tabular-nums'>
            {isLoading ? '...' : `${String(totalEndpoints)} nodes`}
          </span>
        </div>

        {/* Tree content - with custom scrollbar styling */}
        <div className='scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border/50 hover:scrollbar-thumb-border/80 [&::-webkit-scrollbar-thumb]:bg-border/40 [&::-webkit-scrollbar-thumb:hover]:bg-border/60 flex-1 overflow-y-auto p-1.5 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-track]:bg-transparent'>
          {isLoading ? (
            <DirectorySkeleton />
          ) : (
            <div className='space-y-0.5'>
              {/* Folder nodes */}
              {groups?.map((group, index) => (
                <FolderNode
                  key={group.owner_username}
                  group={group}
                  colorIndex={index}
                  defaultOpen={index < 3}
                />
              ))}

              {/* Bottom indicator */}
              {groups && groups.length > 0 && (
                <div className='flex items-center gap-2 px-2 py-1'>
                  <span className='text-muted-foreground/30 font-mono text-[10px]'>
                    {totalContributors} contributors &middot; {totalEndpoints} total nodes
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Browse all link */}
      <Link
        to='/browse'
        className='text-muted-foreground hover:text-foreground group mt-3 flex items-center gap-1 font-mono text-[10px] transition-colors'
      >
        browse all
        <ChevronRight className='h-3 w-3 transition-transform group-hover:translate-x-0.5' />
      </Link>
    </div>
  );
}
