import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { Collective, CollectiveSharedEndpoint } from '@/lib/collectives-api';
import type { ChatSource } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';
import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import Database from 'lucide-react/dist/esm/icons/database';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Layers from 'lucide-react/dist/esm/icons/layers';
import Search from 'lucide-react/dist/esm/icons/search';
import Shield from 'lucide-react/dist/esm/icons/shield';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import Users from 'lucide-react/dist/esm/icons/users';
import { Link } from 'react-router-dom';

import { OnboardingCallout } from '@/components/onboarding';
import { Modal } from '@/components/ui/modal';
import { getPublicEndpointsPaginated, isDataSourceEndpoint } from '@/lib/endpoint-utils';

// ============================================================================
// Helpers — map a Collective to a ChatSource for storage in the context store
// ============================================================================

/**
 * Convert a Collective into the ChatSource shape expected by the context store
 * and the chat workflow. The `full_path` is set to `collective/<slug>`, which
 * the TypeScript SDK detects and resolves to individual endpoint paths before
 * building the aggregator request.
 */
/**
 * Convert a shared endpoint into a ChatSource keyed by both the collective and
 * shared slug. The `full_path` is `collective/<collective-slug>/<shared-slug>`,
 * which the TypeScript SDK recognises and expands to the configured-and-active
 * subset of members at chat time.
 */
function sharedEndpointToChatSource(shared: CollectiveSharedEndpoint): ChatSource {
  return {
    id: `collective:${shared.collective_slug}/${shared.slug}`,
    name: shared.name,
    tags: [],
    description: shared.description,
    type: 'data_source',
    updated: '',
    updated_at: shared.updated_at,
    status: 'active',
    slug: shared.slug,
    stars_count: 0,
    version: '',
    readme: '',
    contributors_count: 0,
    owner_username: undefined,
    full_path: shared.shared_endpoint_path
  };
}

function collectiveToChatSource(collective: Collective): ChatSource {
  return {
    // The id prefix "collective:" makes it unique and avoids clashing with
    // endpoint slugs (which use slug-only IDs). The full_path is what the
    // TypeScript SDK inspects — it detects the "collective/" prefix and
    // resolves it to individual member endpoint paths before the aggregator
    // request is built.
    id: `collective:${collective.slug}`,
    name: collective.name,
    tags: collective.tags,
    description: collective.description,
    // Using 'data_source' keeps ChatSource.type within its declared union
    // while still correctly passing through the chat workflow (which only
    // reads full_path, not type, when building the aggregator request).
    type: 'data_source',
    updated: '',
    updated_at: collective.updated_at,
    status: 'active',
    slug: collective.slug,
    stars_count: 0,
    version: '',
    readme: '',
    contributors_count: 0,
    owner_username: undefined,
    full_path: collective.shared_endpoint_path // "collective/<slug>"
  };
}

// ============================================================================
// Sub-components
// ============================================================================

interface SourceItemProps {
  source: ChatSource;
  isSelected: boolean;
  onToggle: () => void;
}

const SourceItem = memo(function SourceItem({
  source,
  isSelected,
  onToggle
}: Readonly<SourceItemProps>) {
  const detailHref = source.owner_username
    ? `/${source.owner_username}/${source.slug}`
    : `/browse/${source.slug}`;

  return (
    <div
      className={`group flex w-full items-start gap-3 rounded-lg border p-3 transition-all ${
        isSelected
          ? 'border-green-500 bg-green-50 dark:border-green-600 dark:bg-green-950/30'
          : 'border-border bg-card hover:border-green-300 hover:bg-green-50/50 dark:hover:border-green-700 dark:hover:bg-green-950/20'
      }`}
    >
      {/* Checkbox indicator */}
      <button
        type='button'
        onClick={onToggle}
        aria-pressed={isSelected}
        className='mt-1 shrink-0 rounded focus-visible:ring-2 focus-visible:ring-[#272532]/50 focus-visible:outline-none'
      >
        <div
          className={`flex h-5 w-5 items-center justify-center rounded border transition-colors ${
            isSelected
              ? 'border-green-500 bg-green-500 dark:border-green-600 dark:bg-green-600'
              : 'border-input bg-background'
          }`}
          aria-hidden='true'
        >
          {isSelected && <Check className='h-3 w-3 text-white' />}
        </div>
      </button>

      {/* Icon */}
      <button
        type='button'
        onClick={onToggle}
        className='flex shrink-0 items-start focus-visible:outline-none'
        tabIndex={-1}
      >
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${
            isSelected
              ? 'bg-green-500 text-white'
              : 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
          }`}
        >
          <Database className='h-4 w-4' />
        </div>
      </button>

      {/* Content */}
      <button
        type='button'
        onClick={onToggle}
        className='min-w-0 flex-1 text-left focus-visible:outline-none'
        tabIndex={-1}
      >
        <span
          className='font-inter text-foreground block truncate text-sm font-medium'
          title={source.name}
        >
          {source.name}
        </span>
        {source.full_path && (
          <span className='font-inter text-muted-foreground block truncate text-xs'>
            {source.full_path}
          </span>
        )}
        {source.description && (
          <p className='font-inter text-muted-foreground mt-1 line-clamp-2 text-xs'>
            {source.description}
          </p>
        )}
      </button>

      {/* Endpoint page link */}
      <Link
        to={detailHref}
        target='_blank'
        rel='noopener noreferrer'
        className='text-muted-foreground hover:text-foreground mt-1 shrink-0 transition-colors'
        aria-label={`View ${source.name} details`}
        onClick={(e) => {
          e.stopPropagation();
        }}
      >
        <ExternalLink className='h-4 w-4' />
      </Link>
    </div>
  );
});

interface ScopeRowProps {
  selected: boolean;
  /** Superseded by an "Entire collective" selection — shown dimmed + disabled. */
  covered?: boolean;
  onToggle: () => void;
  icon?: React.ReactNode;
  title: string;
  subtitle: string;
  /** The "Entire collective" row gets a faint distinct tint vs. the named APIs. */
  accent?: boolean;
}

/**
 * A single selectable scope inside a collective card — either the whole
 * collective or one of its Collective APIs. Checkbox + title + member count,
 * with a clear selected state and a "covered" (included) state when the whole
 * collective is already chosen.
 */
const ScopeRow = memo(function ScopeRow({
  selected,
  covered = false,
  onToggle,
  icon,
  title,
  subtitle,
  accent = false
}: Readonly<ScopeRowProps>) {
  return (
    <button
      type='button'
      onClick={covered ? undefined : onToggle}
      disabled={covered}
      aria-pressed={selected}
      className={`group flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left transition-all focus-visible:ring-2 focus-visible:ring-indigo-500/40 focus-visible:outline-none ${
        selected
          ? 'border-indigo-500 bg-indigo-50 dark:border-indigo-600 dark:bg-indigo-950/40'
          : covered
            ? 'cursor-default border-transparent opacity-55'
            : accent
              ? 'border-indigo-200/70 bg-indigo-50/40 hover:border-indigo-300 hover:bg-indigo-50/70 dark:border-indigo-900/70 dark:bg-indigo-950/15 dark:hover:border-indigo-700'
              : 'border-border bg-card hover:border-indigo-300 hover:bg-indigo-50/40 dark:hover:border-indigo-700 dark:hover:bg-indigo-950/20'
      }`}
    >
      <span
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors ${
          selected
            ? 'border-indigo-500 bg-indigo-500 dark:border-indigo-600 dark:bg-indigo-600'
            : 'border-input bg-background'
        }`}
        aria-hidden='true'
      >
        {selected && <Check className='h-3 w-3 text-white' />}
      </span>
      {icon && (
        <span
          className={`shrink-0 ${selected ? 'text-indigo-600 dark:text-indigo-300' : 'text-muted-foreground'}`}
          aria-hidden='true'
        >
          {icon}
        </span>
      )}
      <span className='min-w-0 flex-1'>
        <span className='font-inter text-foreground block truncate text-sm font-medium'>
          {title}
        </span>
        <span className='font-inter text-muted-foreground block truncate text-[11px]'>
          {subtitle}
        </span>
      </span>
      {covered && (
        <span className='bg-muted text-muted-foreground shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium'>
          Included
        </span>
      )}
    </button>
  );
});

interface CollectiveGroupCardProps {
  collective: Collective;
  sharedEndpoints: CollectiveSharedEndpoint[];
  wholeSelected: boolean;
  selectedInGroup: number;
  isExpanded: boolean;
  onToggleExpand: () => void;
  onToggleWhole: () => void;
  isSharedSelected: (shared: CollectiveSharedEndpoint) => boolean;
  onToggleShared: (shared: CollectiveSharedEndpoint) => void;
}

/**
 * A collective rendered as a self-contained group card: an identity header that
 * collapses/expands, an explicit "Entire collective" scope, and the collective's
 * named APIs as clearly-secondary scopes. The card (a Gestalt common region)
 * carries the grouping, so the whole-vs-subset relationship reads at a glance.
 */
const CollectiveGroupCard = memo(function CollectiveGroupCard({
  collective,
  sharedEndpoints,
  wholeSelected,
  selectedInGroup,
  isExpanded,
  onToggleExpand,
  onToggleWhole,
  isSharedSelected,
  onToggleShared
}: Readonly<CollectiveGroupCardProps>) {
  const apiCount = sharedEndpoints.length;
  const endpointLabel = collective.member_count === 1 ? 'endpoint' : 'endpoints';
  return (
    <div
      className={`overflow-hidden rounded-xl border transition-colors ${
        selectedInGroup > 0 ? 'border-indigo-300 dark:border-indigo-800' : 'border-border'
      }`}
    >
      {/* Header — identity + collapse only; never a selection control */}
      <div className='bg-muted/40 flex items-center gap-2.5 p-2.5'>
        <button
          type='button'
          onClick={onToggleExpand}
          aria-expanded={isExpanded}
          aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${collective.name}`}
          className='text-muted-foreground hover:text-foreground hover:bg-accent flex h-6 w-6 shrink-0 items-center justify-center rounded-md transition-colors focus-visible:ring-2 focus-visible:ring-indigo-500/40 focus-visible:outline-none'
        >
          <ChevronDown
            className={`h-4 w-4 transition-transform duration-200 ${isExpanded ? '' : '-rotate-90'}`}
          />
        </button>
        <div className='flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-900/60 dark:text-indigo-300'>
          <Users className='h-4 w-4' />
        </div>
        <button
          type='button'
          onClick={onToggleExpand}
          className='min-w-0 flex-1 text-left focus-visible:outline-none'
          tabIndex={-1}
        >
          <span className='font-inter text-foreground flex items-center gap-1 truncate text-sm font-semibold'>
            {collective.name}
            {collective.verified && (
              <ShieldCheck
                className='h-3.5 w-3.5 shrink-0 text-emerald-500'
                aria-label='Verified'
              />
            )}
          </span>
          <span className='font-inter text-muted-foreground block truncate text-[11px]'>
            {collective.member_count} {endpointLabel}
            {apiCount > 0 && ` · ${String(apiCount)} ${apiCount === 1 ? 'API' : 'APIs'}`}
          </span>
        </button>
        {selectedInGroup > 0 && (
          <span className='shrink-0 rounded-full bg-indigo-500 px-2 py-0.5 text-[10px] font-semibold text-white'>
            {selectedInGroup} selected
          </span>
        )}
        <Link
          to={`/c/${collective.slug}`}
          target='_blank'
          rel='noopener noreferrer'
          className='text-muted-foreground hover:text-foreground hover:bg-accent flex h-6 w-6 shrink-0 items-center justify-center rounded-md transition-colors'
          aria-label={`View ${collective.name}`}
          onClick={(e) => {
            e.stopPropagation();
          }}
        >
          <ExternalLink className='h-3.5 w-3.5' />
        </Link>
      </div>

      {/* Body — scopes */}
      {isExpanded && (
        <div className='space-y-1 p-2'>
          <ScopeRow
            selected={wholeSelected}
            onToggle={onToggleWhole}
            icon={<Layers className='h-4 w-4' />}
            title='Entire collective'
            subtitle={`All ${String(collective.member_count)} ${endpointLabel}`}
            accent
          />
          {apiCount > 0 && (
            <p className='font-inter text-muted-foreground px-1 pt-1.5 pb-0.5 text-[10px] font-semibold tracking-wider uppercase'>
              Collective APIs
            </p>
          )}
          {sharedEndpoints.map((shared) => (
            <ScopeRow
              key={shared.slug}
              selected={isSharedSelected(shared)}
              covered={wholeSelected}
              onToggle={() => {
                onToggleShared(shared);
              }}
              title={shared.name}
              subtitle={`${String(shared.active_member_count)} of ${String(shared.member_count)} endpoints`}
            />
          ))}
        </div>
      )}
    </div>
  );
});

// ============================================================================
// Main Component
// ============================================================================

type ActiveTab = 'endpoints' | 'collectives';

export interface AddSourcesModalProps {
  isOpen: boolean;
  onClose: () => void;
  availableSources: ChatSource[];
  selectedSourceIds: Set<string>;
  onConfirm: (selectedSources: ChatSource[]) => void;
  /** Collectives to show in the Collectives tab. Pass an empty array to hide the tab. */
  availableCollectives?: Collective[];
  /**
   * Curated shared-endpoint subsets, paired with their parent collective.
   *
   * Rendered as indented child rows under each parent in the Collectives tab.
   * Empty when no collective in `availableCollectives` has any named subsets;
   * the parent rows still work as before in that case.
   */
  availableSharedEndpoints?: Array<{
    collective: Collective;
    shared: CollectiveSharedEndpoint;
  }>;
}

export const AddSourcesModal = memo(function AddSourcesModal({
  isOpen,
  onClose,
  availableSources,
  selectedSourceIds,
  onConfirm,
  availableCollectives = [],
  availableSharedEndpoints = []
}: Readonly<AddSourcesModalProps>) {
  const [activeTab, setActiveTab] = useState<ActiveTab>('endpoints');
  // Local selection state — only committed on confirm
  const [localSelected, setLocalSelected] = useState<Set<string>>(new Set(selectedSourceIds));
  // Resolved source objects for all currently selected IDs (needed for search results not in availableSources)
  const [resolvedSourcesMap, setResolvedSourcesMap] = useState<Map<string, ChatSource>>(new Map());
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<ChatSource[] | null>(null);
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  // Collapsed collective cards (by slug). Empty = all expanded.
  const [collapsedCollectives, setCollapsedCollectives] = useState<Set<string>>(new Set());

  const showCollectivesTab = availableCollectives.length > 0;

  // Sync local state when modal opens with new external selections
  const previousOpenReference = useRef(false);
  useEffect(() => {
    if (isOpen && !previousOpenReference.current) {
      setLocalSelected(new Set(selectedSourceIds));
      // Rebuild resolved map from pre-loaded sources matching the initial selection
      const initialMap = new Map<string, ChatSource>();
      for (const source of availableSources) {
        if (selectedSourceIds.has(source.id)) {
          initialMap.set(source.id, source);
        }
      }
      // Also restore any selected collective sources
      for (const collective of availableCollectives) {
        const id = `collective:${collective.slug}`;
        if (selectedSourceIds.has(id)) {
          initialMap.set(id, collectiveToChatSource(collective));
        }
      }
      // ... and any selected shared-endpoint subsets.
      for (const { shared } of availableSharedEndpoints) {
        const id = `collective:${shared.collective_slug}/${shared.slug}`;
        if (selectedSourceIds.has(id)) {
          initialMap.set(id, sharedEndpointToChatSource(shared));
        }
      }
      setResolvedSourcesMap(initialMap);
      setSearchQuery('');
      setDebouncedSearchQuery('');
      setSearchResults(null);
      setActiveTab('endpoints');
    }
    previousOpenReference.current = isOpen;
  }, [isOpen, selectedSourceIds, availableSources, availableCollectives, availableSharedEndpoints]);

  // Reset search when switching tabs
  const handleTabChange = useCallback((tab: ActiveTab) => {
    setActiveTab(tab);
    setSearchQuery('');
    setDebouncedSearchQuery('');
    setSearchResults(null);
  }, []);

  // Debounce searchQuery → debouncedSearchQuery (300ms, matching Browse page)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery);
    }, 300);
    return () => {
      clearTimeout(timer);
    };
  }, [searchQuery]);

  // Server-side endpoint search (endpoints tab only)
  useEffect(() => {
    if (activeTab !== 'endpoints') return;
    if (!debouncedSearchQuery.trim()) {
      setSearchResults(null);
      setIsSearchLoading(false);
      return;
    }

    let cancelled = false;
    setIsSearchLoading(true);

    void getPublicEndpointsPaginated({
      limit: 20,
      endpoint_type: 'data_source',
      search: debouncedSearchQuery.trim()
    }).then((result) => {
      if (!cancelled) {
        setSearchResults(result.items);
        setIsSearchLoading(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [debouncedSearchQuery, activeTab]);

  // Pre-loaded list filtered to data sources only (used when not searching)
  const dataSourceEndpoints = useMemo(
    () => availableSources.filter((s) => isDataSourceEndpoint(s.type)),
    [availableSources]
  );

  // Collectives filtered locally by search query. A collective is included
  // when EITHER the parent fields match OR at least one of its shared
  // endpoints matches — shared endpoints are first-class selectable items,
  // so 'health-news' must surface its parent collective even when the
  // parent name doesn't mention 'health-news'.
  const filteredCollectives = useMemo(() => {
    if (!debouncedSearchQuery.trim()) return availableCollectives;
    const q = debouncedSearchQuery.toLowerCase();
    const sharedByParentSlug = new Map<string, CollectiveSharedEndpoint[]>();
    for (const { collective, shared } of availableSharedEndpoints) {
      const list = sharedByParentSlug.get(collective.slug);
      if (list) {
        list.push(shared);
      } else {
        sharedByParentSlug.set(collective.slug, [shared]);
      }
    }
    return availableCollectives.filter((c) => {
      if (
        c.name.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q) ||
        c.slug.toLowerCase().includes(q) ||
        c.tags.some((t) => t.toLowerCase().includes(q))
      ) {
        return true;
      }
      const shared = sharedByParentSlug.get(c.slug) ?? [];
      return shared.some(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.slug.toLowerCase().includes(q) ||
          s.description.toLowerCase().includes(q)
      );
    });
  }, [availableCollectives, availableSharedEndpoints, debouncedSearchQuery]);

  // Sorted endpoints: selected bubble to top
  const sortedSources = useMemo(() => {
    const activeSources = searchResults ?? dataSourceEndpoints;
    return activeSources.toSorted((a, b) => {
      const aSelected = localSelected.has(a.id) ? 0 : 1;
      const bSelected = localSelected.has(b.id) ? 0 : 1;
      return aSelected - bSelected;
    });
  }, [searchResults, dataSourceEndpoints, localSelected]);

  // Sorted collectives: selected bubble to top
  const sortedCollectives = useMemo(() => {
    return filteredCollectives.toSorted((a, b) => {
      const aId = `collective:${a.slug}`;
      const bId = `collective:${b.slug}`;
      const aSelected = localSelected.has(aId) ? 0 : 1;
      const bSelected = localSelected.has(bId) ? 0 : 1;
      return aSelected - bSelected;
    });
  }, [filteredCollectives, localSelected]);

  // Shared endpoints indexed by parent collective slug. The grouping is cheap
  // even for thousands of entries (single pass) and saves a per-row lookup
  // while rendering.
  const sharedByCollective = useMemo(() => {
    const map = new Map<string, CollectiveSharedEndpoint[]>();
    for (const { collective, shared } of availableSharedEndpoints) {
      const list = map.get(collective.slug);
      if (list) {
        list.push(shared);
      } else {
        map.set(collective.slug, [shared]);
      }
    }
    return map;
  }, [availableSharedEndpoints]);

  const toggleEndpoint = useCallback((source: ChatSource) => {
    setLocalSelected((previous) => {
      const next = new Set(previous);
      if (next.has(source.id)) {
        next.delete(source.id);
      } else {
        next.add(source.id);
      }
      return next;
    });
    setResolvedSourcesMap((previous) => {
      const next = new Map(previous);
      if (next.has(source.id)) {
        next.delete(source.id);
      } else {
        next.set(source.id, source);
      }
      return next;
    });
  }, []);

  const toggleCollapse = useCallback((slug: string) => {
    setCollapsedCollectives((previous) => {
      const next = new Set(previous);
      if (next.has(slug)) {
        next.delete(slug);
      } else {
        next.add(slug);
      }
      return next;
    });
  }, []);

  const toggleCollective = useCallback(
    (collective: Collective) => {
      const id = `collective:${collective.slug}`;
      const chatSource = collectiveToChatSource(collective);
      // Selecting the whole collective supersedes any of its named API subsets,
      // so drop those to keep the selection unambiguous (and avoid double-billing).
      const subsetIds = (sharedByCollective.get(collective.slug) ?? []).map(
        (s) => `collective:${s.collective_slug}/${s.slug}`
      );
      setLocalSelected((previous) => {
        const next = new Set(previous);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
          for (const sid of subsetIds) next.delete(sid);
        }
        return next;
      });
      setResolvedSourcesMap((previous) => {
        const next = new Map(previous);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.set(id, chatSource);
          for (const sid of subsetIds) next.delete(sid);
        }
        return next;
      });
    },
    [sharedByCollective]
  );

  const toggleSharedEndpoint = useCallback((shared: CollectiveSharedEndpoint) => {
    const id = `collective:${shared.collective_slug}/${shared.slug}`;
    const chatSource = sharedEndpointToChatSource(shared);
    setLocalSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
    setResolvedSourcesMap((previous) => {
      const next = new Map(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.set(id, chatSource);
      }
      return next;
    });
  }, []);

  const handleConfirm = useCallback(() => {
    const selectedSources = [...resolvedSourcesMap.values()];
    onConfirm(selectedSources);
  }, [resolvedSourcesMap, onConfirm]);

  const handleSearchChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(event.target.value);
  }, []);

  const selectedCount = localSelected.size;
  const isSearching = searchQuery.trim().length > 0;

  return (
    <Modal isOpen={isOpen} onClose={onClose} size='lg' showCloseButton={false}>
      {/* Header */}
      <div className='flex items-center gap-3 pb-4'>
        <div className='flex h-10 w-10 items-center justify-center rounded-lg bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'>
          <Database className='h-5 w-5' />
        </div>
        <div>
          <h3 className='font-inter text-foreground text-base font-medium'>
            Add Sources to Context
          </h3>
          <p className='font-inter text-muted-foreground text-xs'>
            Choose sources to ground your answer.
          </p>
        </div>
      </div>

      {/* Tab switcher — only shown when there are collectives to display */}
      {showCollectivesTab && (
        <div className='mb-3 flex gap-1 rounded-lg border p-1'>
          <button
            type='button'
            onClick={() => {
              handleTabChange('endpoints');
            }}
            className={`font-inter flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeTab === 'endpoints'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Database className='h-3.5 w-3.5' />
            Data Sources
          </button>
          <button
            type='button'
            onClick={() => {
              handleTabChange('collectives');
            }}
            className={`font-inter flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeTab === 'collectives'
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Shield className='h-3.5 w-3.5' />
            Collectives
          </button>
        </div>
      )}

      {/* Search input */}
      <div className='relative mb-3'>
        <Search className='text-muted-foreground pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2' />
        <input
          type='text'
          value={searchQuery}
          onChange={handleSearchChange}
          placeholder={activeTab === 'collectives' ? 'Search collectives…' : 'Search endpoints...'}
          className='font-inter border-border bg-background placeholder:text-muted-foreground w-full rounded-lg border py-2 pr-4 pl-10 text-sm transition-colors focus:border-green-500 focus:ring-2 focus:ring-green-500/20 focus:outline-none'
          autoComplete='off'
        />
      </div>

      {/* Onboarding callout for source selection */}
      {activeTab === 'endpoints' && (
        <OnboardingCallout step='select-sources' position='bottom'>
          <div />
        </OnboardingCallout>
      )}

      {/* Scrollable list */}
      <div className='max-h-72 space-y-2 overflow-y-auto pr-1'>
        {activeTab === 'endpoints' ? (
          isSearchLoading ? (
            <div className='py-8 text-center'>
              <p className='font-inter text-muted-foreground text-sm'>Searching...</p>
            </div>
          ) : sortedSources.length > 0 ? (
            sortedSources.map((source) => (
              <SourceItem
                key={source.id}
                source={source}
                isSelected={localSelected.has(source.id)}
                onToggle={() => {
                  toggleEndpoint(source);
                }}
              />
            ))
          ) : (
            <div className='py-8 text-center'>
              <p className='font-inter text-muted-foreground text-sm'>
                {isSearching ? 'No matching data sources found' : 'No data sources available'}
              </p>
            </div>
          )
        ) : sortedCollectives.length > 0 ? (
          sortedCollectives.map((collective) => {
            const sharedEndpoints = sharedByCollective.get(collective.slug) ?? [];
            const queryLower = debouncedSearchQuery.toLowerCase();
            // When searching, narrow the card's visible APIs to those that match too.
            const matchingShared = queryLower
              ? sharedEndpoints.filter(
                  (shared) =>
                    shared.name.toLowerCase().includes(queryLower) ||
                    shared.slug.toLowerCase().includes(queryLower) ||
                    shared.description.toLowerCase().includes(queryLower)
                )
              : sharedEndpoints;
            const wholeSelected = localSelected.has(`collective:${collective.slug}`);
            const selectedSubsets = matchingShared.filter((shared) =>
              localSelected.has(`collective:${collective.slug}/${shared.slug}`)
            ).length;
            return (
              <CollectiveGroupCard
                key={collective.slug}
                collective={collective}
                sharedEndpoints={matchingShared}
                wholeSelected={wholeSelected}
                selectedInGroup={(wholeSelected ? 1 : 0) + selectedSubsets}
                isExpanded={isSearching || !collapsedCollectives.has(collective.slug)}
                onToggleExpand={() => {
                  toggleCollapse(collective.slug);
                }}
                onToggleWhole={() => {
                  toggleCollective(collective);
                }}
                isSharedSelected={(shared) =>
                  localSelected.has(`collective:${collective.slug}/${shared.slug}`)
                }
                onToggleShared={toggleSharedEndpoint}
              />
            );
          })
        ) : (
          <div className='py-8 text-center'>
            <p className='font-inter text-muted-foreground text-sm'>
              {isSearching ? 'No matching collectives found' : 'No collectives available'}
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className='flex items-center justify-end gap-2 pt-4'>
        <button
          type='button'
          onClick={onClose}
          className='font-inter text-muted-foreground hover:text-foreground hover:bg-accent rounded-lg px-4 py-2 text-sm transition-colors'
        >
          Cancel
        </button>
        <button
          type='button'
          onClick={handleConfirm}
          className='font-inter flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50'
        >
          {selectedCount === 0
            ? 'Confirm'
            : `Confirm ${String(selectedCount)} Source${selectedCount === 1 ? '' : 's'}`}
        </button>
      </div>
    </Modal>
  );
});
