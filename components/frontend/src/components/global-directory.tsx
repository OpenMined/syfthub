import { useCallback, useMemo, useState } from 'react';

import type { ChatSource } from '@/lib/types';

import ChevronRight from 'lucide-react/dist/esm/icons/chevron-right';
import Cpu from 'lucide-react/dist/esm/icons/cpu';
import Database from 'lucide-react/dist/esm/icons/database';
import Folder from 'lucide-react/dist/esm/icons/folder';
import FolderOpen from 'lucide-react/dist/esm/icons/folder-open';
import { Link } from 'react-router-dom';

// =============================================================================
// Types
// =============================================================================

interface DirectoryNode {
  owner: string;
  endpoints: ChatSource[];
}

interface GlobalDirectoryProps {
  endpoints: ChatSource[];
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

function FolderNode({
  node,
  colorIndex,
  defaultOpen
}: Readonly<{
  node: DirectoryNode;
  colorIndex: number;
  defaultOpen: boolean;
}>) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const color = getNodeColor(colorIndex);

  const toggle = useCallback(() => {
    setIsOpen((previous) => !previous);
  }, []);

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
          {node.owner}/
        </span>

        {/* Count */}
        <span className='text-muted-foreground font-mono text-[10px] tabular-nums'>
          {node.endpoints.length} {node.endpoints.length === 1 ? 'node' : 'nodes'}
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
          {node.endpoints.map((endpoint, index) => (
            <DirectoryEntry
              key={endpoint.id}
              endpoint={endpoint}
              depth={1}
              colorIndex={colorIndex + index}
            />
          ))}
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

export function GlobalDirectory({ endpoints, isLoading }: Readonly<GlobalDirectoryProps>) {
  // Group endpoints by owner into directory tree
  const directoryTree = useMemo(() => {
    const ownerMap = new Map<string, ChatSource[]>();

    for (const ep of endpoints) {
      const owner = ep.owner_username ?? 'network';
      const existing = ownerMap.get(owner);
      if (existing) {
        existing.push(ep);
      } else {
        ownerMap.set(owner, [ep]);
      }
    }

    // Sort by number of endpoints (descending) for visual weight
    const nodes: DirectoryNode[] = [];
    for (const [owner, eps] of ownerMap) {
      nodes.push({ owner, endpoints: eps });
    }
    nodes.sort((a, b) => b.endpoints.length - a.endpoints.length);

    return nodes;
  }, [endpoints]);

  if (!isLoading && endpoints.length === 0) {
    return null;
  }

  return (
    <div className='flex h-full flex-col'>
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
      <div className='bg-background/80 border-border/30 flex h-full flex-col overflow-hidden rounded-lg border'>
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
            {isLoading ? '...' : `${String(endpoints.length)} nodes`}
          </span>
        </div>

        {/* Tree content */}
        <div className='flex-1 overflow-y-auto p-1.5'>
          {isLoading ? (
            <DirectorySkeleton />
          ) : (
            <div className='space-y-0.5'>
              {/* Folder nodes */}
              {directoryTree.map((node, index) => (
                <FolderNode
                  key={node.owner}
                  node={node}
                  colorIndex={index}
                  defaultOpen={index < 3}
                />
              ))}

              {/* Bottom indicator */}
              {directoryTree.length > 0 && (
                <div className='flex items-center gap-2 px-2 py-1'>
                  <span className='text-muted-foreground/30 font-mono text-[10px]'>
                    {directoryTree.length} contributors &middot; {endpoints.length} total nodes
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
