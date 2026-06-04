/**
 * InviteCombobox
 *
 * A two-phase typeahead for picking endpoints to invite into a collective,
 * mirroring the chat `@owner/slug` mention flow: type a name, get suggestions
 * you can Tab/Enter to complete.
 *
 * - Owner phase: type to filter owners; selecting one drills into their
 *   endpoints (the input shows an `@owner /` token prefix).
 * - Endpoint phase: a pinned "All data sources from @owner" row stages every
 *   joinable endpoint at once (the `owner/*` action); below it, the owner's
 *   individual data-source endpoints.
 *
 * Only `data_source` / `model_data_source` endpoints are ever surfaced, mirroring
 * the backend `_require_joinable_endpoint` guard. Selection is delegated to the
 * parent, which stages picks as removable chips.
 */
import { useEffect, useMemo, useRef, useState } from 'react';

import type { OwnerInfo } from '@/lib/mention-utils';
import type { ChatSource } from '@/lib/types';

import { useQuery } from '@tanstack/react-query';
import Check from 'lucide-react/dist/esm/icons/check';
import Database from 'lucide-react/dist/esm/icons/database';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Search from 'lucide-react/dist/esm/icons/search';
import User from 'lucide-react/dist/esm/icons/user';
import Users from 'lucide-react/dist/esm/icons/users';
import X from 'lucide-react/dist/esm/icons/x';

import { useEndpointsByOwner } from '@/hooks/use-endpoint-queries';
import { isJoinableEndpointType } from '@/lib/collectives-api';
import { getPublicEndpointOwners } from '@/lib/endpoint-utils';
import { filterEndpoints, filterOwners } from '@/lib/mention-utils';
import { cn } from '@/lib/utils';

/** A single endpoint the user chose to invite. */
export interface InviteEndpointOption {
  owner: string;
  slug: string;
  name: string;
}

interface InviteComboboxProps {
  /** Stage a single endpoint. */
  onSelectEndpoint: (option: InviteEndpointOption) => void;
  /** Stage every joinable endpoint of an owner (the `owner/*` action). */
  onSelectAll: (owner: string, endpoints: { slug: string; name: string }[]) => void;
  /** `owner/slug` keys already staged — rendered as added and not re-addable. */
  stagedKeys: ReadonlySet<string>;
  /** Owners already staged via an all-* chip — their rows are shown as covered. */
  stagedAllOwners: ReadonlySet<string>;
}

type Row =
  | { type: 'owner'; owner: OwnerInfo }
  | { type: 'all'; owner: string; count: number; staged: boolean }
  | { type: 'endpoint'; endpoint: ChatSource; itemKey: string; staged: boolean };

export function InviteCombobox({
  onSelectEndpoint,
  onSelectAll,
  stagedKeys,
  stagedAllOwners
}: Readonly<InviteComboboxProps>) {
  const [selectedOwner, setSelectedOwner] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  const containerReference = useRef<HTMLDivElement>(null);
  const inputReference = useRef<HTMLInputElement>(null);
  const listReference = useRef<HTMLUListElement>(null);
  // True when the highlight last moved via keyboard, so we only auto-scroll for
  // arrow-key navigation — not when the mouse hovers a row.
  const keyboardNavReference = useRef(false);

  const phase: 'owner' | 'endpoint' = selectedOwner ? 'endpoint' : 'owner';

  const { data: owners = [], isLoading: ownersLoading } = useQuery({
    queryKey: ['public-endpoint-owners'],
    queryFn: getPublicEndpointOwners,
    staleTime: 5 * 60 * 1000
  });

  const { data: ownerEndpoints = [], isFetching: endpointsLoading } = useEndpointsByOwner(
    selectedOwner ?? undefined
  );

  const joinable = useMemo(
    () => ownerEndpoints.filter((endpoint) => isJoinableEndpointType(endpoint.type)),
    [ownerEndpoints]
  );

  const filteredOwners = useMemo(
    () => (phase === 'owner' ? filterOwners(owners, query, 8) : []),
    [phase, owners, query]
  );
  const filteredEndpoints = useMemo(
    () => (phase === 'endpoint' ? filterEndpoints(joinable, query, 8) : []),
    [phase, joinable, query]
  );

  const rows: Row[] = useMemo(() => {
    if (phase === 'owner') {
      return filteredOwners.map((owner) => ({ type: 'owner', owner }) as Row);
    }
    const owner = selectedOwner ?? '';
    const list: Row[] = [];
    if (joinable.length > 0) {
      list.push({ type: 'all', owner, count: joinable.length, staged: stagedAllOwners.has(owner) });
    }
    for (const endpoint of filteredEndpoints) {
      const itemKey = `${owner}/${endpoint.slug}`;
      list.push({
        type: 'endpoint',
        endpoint,
        itemKey,
        staged: stagedAllOwners.has(owner) || stagedKeys.has(itemKey)
      });
    }
    return list;
  }, [
    phase,
    filteredOwners,
    filteredEndpoints,
    joinable,
    selectedOwner,
    stagedKeys,
    stagedAllOwners
  ]);

  const loading = phase === 'owner' ? ownersLoading : endpointsLoading;

  // Reset the highlight whenever the visible list changes.
  useEffect(() => {
    setHighlightedIndex(0);
  }, [phase, query, rows.length]);

  // Keep the keyboard-highlighted row scrolled into view (skip mouse hover, which
  // would trigger a layout-reading scrollIntoView on every pointer move).
  useEffect(() => {
    if (!keyboardNavReference.current) return;
    const node = listReference.current?.children[highlightedIndex] as HTMLElement | undefined;
    node?.scrollIntoView({ block: 'nearest' });
  }, [highlightedIndex]);

  // Close the dropdown on an outside click.
  useEffect(() => {
    function onDocumentMouseDown(event: MouseEvent) {
      if (
        containerReference.current &&
        !containerReference.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocumentMouseDown);
    return () => {
      document.removeEventListener('mousedown', onDocumentMouseDown);
    };
  }, []);

  const focusInput = () => {
    setTimeout(() => inputReference.current?.focus(), 0);
  };

  const clearOwner = () => {
    setSelectedOwner(null);
    setQuery('');
    focusInput();
  };

  const chooseRow = (row: Row) => {
    if (row.type === 'owner') {
      setSelectedOwner(row.owner.username);
      setQuery('');
      setOpen(true);
      focusInput();
      return;
    }
    if (row.type === 'all') {
      if (row.staged) return;
      onSelectAll(
        row.owner,
        joinable.map((endpoint) => ({ slug: endpoint.slug, name: endpoint.name }))
      );
      // Everything from this owner is staged — drop back to owner phase so the
      // user can move on to another owner.
      clearOwner();
      return;
    }
    if (row.staged) return;
    onSelectEndpoint({
      owner: selectedOwner ?? row.endpoint.owner_username ?? '',
      slug: row.endpoint.slug,
      name: row.endpoint.name
    });
    // Stay in endpoint phase so several picks from the same owner are quick.
    setQuery('');
    focusInput();
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case 'ArrowDown': {
        event.preventDefault();
        setOpen(true);
        keyboardNavReference.current = true;
        setHighlightedIndex((index) => Math.min(index + 1, rows.length - 1));

        break;
      }
      case 'ArrowUp': {
        event.preventDefault();
        keyboardNavReference.current = true;
        setHighlightedIndex((index) => Math.max(index - 1, 0));

        break;
      }
      case 'Enter':
      case 'Tab': {
        const row = rows[highlightedIndex];
        if (open && row) {
          event.preventDefault();
          chooseRow(row);
        }

        break;
      }
      default: {
        if (event.key === 'Backspace' && query === '' && selectedOwner) {
          event.preventDefault();
          clearOwner();
        } else if (event.key === 'Escape' && open) {
          event.preventDefault();
          setOpen(false);
        }
      }
    }
  };

  return (
    <div ref={containerReference} className='relative'>
      <div className='border-input bg-background/50 focus-within:border-primary focus-within:ring-primary/20 flex h-11 items-center gap-2 rounded-lg border px-3 shadow-sm backdrop-blur-sm transition-all focus-within:ring-2'>
        <Search className='text-muted-foreground h-4 w-4 shrink-0' aria-hidden />
        {selectedOwner && (
          <span className='bg-muted text-foreground inline-flex shrink-0 items-center gap-1 rounded-md py-0.5 pr-1 pl-1.5 text-sm'>
            @{selectedOwner}
            <span className='text-muted-foreground'>/</span>
            <button
              type='button'
              aria-label={`Clear ${selectedOwner}`}
              onClick={clearOwner}
              className='text-muted-foreground hover:text-foreground'
            >
              <X className='h-3 w-3' />
            </button>
          </span>
        )}
        <input
          ref={inputReference}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => {
            setOpen(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder={selectedOwner ? 'Filter endpoints…' : 'Search by owner or endpoint…'}
          className='placeholder:text-muted-foreground/70 h-full flex-1 bg-transparent text-sm outline-none'
          role='combobox'
          aria-expanded={open}
          aria-controls='invite-combobox-list'
          aria-autocomplete='list'
          aria-activedescendant={
            open && rows[highlightedIndex] ? `invite-row-${highlightedIndex}` : undefined
          }
        />
      </div>

      {open && (
        <div
          id='invite-combobox-list'
          role='listbox'
          aria-label={selectedOwner ? 'Select endpoints' : 'Select an owner'}
          className='bg-popover text-popover-foreground absolute top-full z-50 mt-2 w-full overflow-hidden rounded-lg border p-1 shadow-lg'
        >
          {loading && rows.length === 0 ? (
            <div className='text-muted-foreground flex items-center justify-center gap-2 py-6 text-sm'>
              <Loader2 className='h-4 w-4 animate-spin' />
              {phase === 'owner' ? 'Loading owners…' : 'Loading endpoints…'}
            </div>
          ) : rows.length === 0 ? (
            <p className='text-muted-foreground px-2 py-6 text-center text-sm'>
              {emptyStateMessage(phase, joinable.length === 0, selectedOwner ?? '')}
            </p>
          ) : (
            <ul ref={listReference} className='max-h-64 overflow-y-auto'>
              {rows.map((row, index) => (
                <RowItem
                  key={rowKey(row)}
                  id={`invite-row-${index}`}
                  row={row}
                  highlighted={index === highlightedIndex}
                  onMouseEnter={() => {
                    keyboardNavReference.current = false;
                    setHighlightedIndex(index);
                  }}
                  onSelect={() => {
                    chooseRow(row);
                  }}
                />
              ))}
            </ul>
          )}
          <div className='text-muted-foreground flex items-center gap-3 border-t px-2 py-1.5 text-xs'>
            <span>
              <kbd className='bg-muted rounded px-1 font-mono'>↑↓</kbd> navigate
            </span>
            <span>
              <kbd className='bg-muted rounded px-1 font-mono'>Tab</kbd> select
            </span>
            <span>
              <kbd className='bg-muted rounded px-1 font-mono'>Esc</kbd> close
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

/** Message shown when the dropdown has no rows to offer. */
function emptyStateMessage(
  phase: 'owner' | 'endpoint',
  ownerHasNoJoinable: boolean,
  owner: string
): string {
  if (phase === 'owner') return 'No matching owners.';
  if (ownerHasNoJoinable) return `@${owner} has no data-source endpoints to invite.`;
  return 'No matching endpoints.';
}

function rowKey(row: Row): string {
  if (row.type === 'owner') return `owner:${row.owner.username}`;
  if (row.type === 'all') return `all:${row.owner}`;
  return `ep:${row.itemKey}`;
}

interface RowItemProps {
  id: string;
  row: Row;
  highlighted: boolean;
  onMouseEnter: () => void;
  onSelect: () => void;
}

function RowItem({ id, row, highlighted, onMouseEnter, onSelect }: Readonly<RowItemProps>) {
  const isStaged = row.type !== 'owner' && row.staged;
  return (
    <li
      id={id}
      role='option'
      aria-selected={highlighted}
      aria-disabled={isStaged}
      onMouseEnter={onMouseEnter}
      onMouseDown={(event) => {
        // Keep focus on the input so selection doesn't blur-close the dropdown.
        event.preventDefault();
      }}
      onClick={onSelect}
      className={cn(
        'flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors',
        isStaged && 'cursor-default opacity-60',
        highlighted && !isStaged ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
      )}
    >
      {row.type === 'owner' && (
        <>
          <span className='bg-muted flex h-6 w-6 shrink-0 items-center justify-center rounded-full'>
            <User className='h-3.5 w-3.5' />
          </span>
          <span className='font-medium'>{row.owner.username}</span>
          <span className='text-muted-foreground text-xs'>
            {row.owner.endpointCount} endpoint{row.owner.endpointCount === 1 ? '' : 's'}
          </span>
        </>
      )}

      {row.type === 'all' && (
        <>
          <span className='bg-primary/10 text-primary flex h-6 w-6 shrink-0 items-center justify-center rounded-full'>
            <Users className='h-3.5 w-3.5' />
          </span>
          <span className='text-foreground flex-1 font-medium'>
            All data sources from @{row.owner}
          </span>
          <span className='text-muted-foreground text-xs'>({row.count})</span>
          {row.staged && <Check className='text-primary h-4 w-4' aria-label='Added' />}
        </>
      )}

      {row.type === 'endpoint' && (
        <>
          <span className='bg-muted flex h-6 w-6 shrink-0 items-center justify-center rounded-full'>
            <Database className='h-3.5 w-3.5' />
          </span>
          <span className='min-w-0 flex-1 truncate font-medium'>{row.endpoint.name}</span>
          <span className='text-muted-foreground shrink-0 text-xs'>{row.endpoint.type}</span>
          {row.staged && <Check className='text-primary h-4 w-4 shrink-0' aria-label='Added' />}
        </>
      )}
    </li>
  );
}
