import { useState, useMemo } from 'react';
import { Search, Settings, FolderOpen, Plus, ShieldCheck, Store, Loader2, AlertCircle, SlidersHorizontal, Check } from 'lucide-react';
import { useAppStore, RuntimeState, type EndpointInfo } from '../stores/appStore';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { typeLabelsShort } from '@/lib/utils';

// Filter type for endpoints
type TypeFilter = 'all' | 'model' | 'data_source' | 'agent';

// Sidebar props
interface SidebarProps {
  onSettingsClick: () => void;
}

// Interactive status chip - click to toggle service state
function StatusChip() {
  const { status, isLoading, startService, stopService } = useAppStore();
  const state = status.state;

  const isTransitioning = state === 'starting' || state === 'stopping';
  const canInteract = !isLoading && !isTransitioning;

  const handleClick = () => {
    if (!canInteract) return;
    if (state === 'running') {
      stopService();
    } else if (state === 'idle' || state === 'error') {
      startService();
    }
  };

  const config: Record<string, { dot: string; bg: string; hover: string; label: string }> = {
    idle: {
      dot: 'bg-muted-foreground',
      bg: 'bg-secondary/50',
      hover: 'hover:bg-secondary',
      label: 'Idle',
    },
    starting: {
      dot: 'bg-chart-3 animate-pulse',
      bg: 'bg-chart-3/10',
      hover: '',
      label: 'Starting...',
    },
    running: {
      dot: 'bg-chart-2',
      bg: 'bg-chart-2/10',
      hover: 'hover:bg-chart-2/20',
      label: 'Running',
    },
    stopping: {
      dot: 'bg-chart-3 animate-pulse',
      bg: 'bg-chart-3/10',
      hover: '',
      label: 'Stopping...',
    },
    error: {
      dot: 'bg-destructive',
      bg: 'bg-destructive/10',
      hover: 'hover:bg-destructive/20',
      label: 'Error',
    },
  };

  const { dot, bg, hover, label } = config[state] || config.idle;
  const actionHint = state === 'running' ? 'Click to stop' : state === 'idle' || state === 'error' ? 'Click to start' : '';

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={handleClick}
          disabled={!canInteract}
          aria-label={`Service is ${label.toLowerCase()}. ${actionHint}`}
          className={`
            flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium
            transition-colors duration-150
            ${bg} ${canInteract ? hover : ''}
            ${canInteract ? 'cursor-pointer' : 'cursor-default'}
            focus:outline-none focus:ring-2 focus:ring-ring/50
          `}
        >
          <span className={`w-2 h-2 rounded-full ${dot}`} />
          <span className="text-foreground">{label}</span>
        </button>
      </TooltipTrigger>
      {actionHint && (
        <TooltipContent side="right">
          <p>{actionHint}</p>
        </TooltipContent>
      )}
    </Tooltip>
  );
}

// Search input component
function SearchInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search..."
        className="
          w-full h-9 pl-9 pr-3
          bg-card/50
          text-sm text-foreground placeholder:text-muted-foreground
          rounded-lg
          border border-border
          focus:outline-none focus:ring-2 focus:ring-ring/30 focus:border-transparent focus:bg-card/70
          transition-all duration-150
        "
      />
    </div>
  );
}

// Filter popover — replaces the chips row with a compact icon button + dropdown
const filterOptions: { value: TypeFilter; label: string }[] = [
  { value: 'all', label: 'All endpoints' },
  { value: 'model', label: 'Models' },
  { value: 'data_source', label: 'Sources' },
  { value: 'agent', label: 'Agents' },
];

function FilterButton({
  selected,
  onChange,
}: {
  selected: TypeFilter;
  onChange: (filter: TypeFilter) => void;
}) {
  const isFiltered = selected !== 'all';

  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <button
              className={`
                relative flex-shrink-0 w-9 h-9 flex items-center justify-center
                rounded-lg border
                transition-colors duration-150
                focus:outline-none focus:ring-2 focus:ring-ring/30
                ${isFiltered
                  ? 'border-primary/40 bg-primary/10 text-primary'
                  : 'border-border bg-card/50 hover:bg-secondary/50 text-muted-foreground hover:text-foreground'
                }
              `}
              aria-label="Filter endpoints"
            >
              <SlidersHorizontal className="w-4 h-4" />
              {isFiltered && (
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-primary" />
              )}
            </button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          <p>{isFiltered ? `Showing: ${filterOptions.find(f => f.value === selected)?.label}` : 'Filter by type'}</p>
        </TooltipContent>
      </Tooltip>
      <PopoverContent align="start" className="w-40 p-1">
        {filterOptions.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={`
              w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-xs font-medium
              transition-colors duration-100
              ${selected === opt.value
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
              }
            `}
          >
            <Check className={`w-3 h-3 flex-shrink-0 ${selected === opt.value ? 'opacity-100' : 'opacity-0'}`} />
            {opt.label}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}

// Skeleton loading component for endpoint items - matches single row layout
function EndpointSkeleton() {
  return (
    <div className="px-3 py-2 rounded-lg animate-pulse">
      <div className="flex items-center gap-2">
        <div className="h-5 w-12 bg-secondary/40 rounded-md flex-shrink-0" />
        <div className="flex-1 h-4 bg-secondary/30 rounded" />
        <div className="w-2 h-2 rounded-full bg-secondary/30 flex-shrink-0" />
      </div>
    </div>
  );
}

// Skeleton section for loading state
function SidebarSkeleton() {
  return (
    <div className="space-y-1">
      <EndpointSkeleton />
      <EndpointSkeleton />
      <EndpointSkeleton />
      <EndpointSkeleton />
    </div>
  );
}

// Type badge colors - using chart colors for semantic distinction
const typeColors: Record<string, { bg: string; text: string }> = {
  model: { bg: 'bg-primary/20', text: 'text-primary' },
  data_source: { bg: 'bg-chart-4/20', text: 'text-chart-4' },
  model_data_source: { bg: 'bg-blue-500/20', text: 'text-blue-400' },
  agent: { bg: 'bg-purple-500/20', text: 'text-purple-400' },
};

// Derive a human-readable status for an endpoint
type EndpointIndicator = 'ready' | 'installing' | 'setting-up' | 'initializing' | 'setup-incomplete' | 'disabled';

function renderStatusIcon(indicator: EndpointIndicator) {
  switch (indicator) {
    case 'ready':
      return <span className="w-2 h-2 rounded-full bg-chart-2 block" />;
    case 'installing':
    case 'setting-up':
    case 'initializing':
      return <Loader2 className="w-3.5 h-3.5 text-chart-3 animate-spin" />;
    case 'setup-incomplete':
      return <AlertCircle className="w-3.5 h-3.5 text-chart-3" />;
    case 'disabled':
      return <span className="w-2 h-2 rounded-full bg-muted-foreground/50 block" />;
  }
}

function getEndpointStatus(endpoint: EndpointInfo): {
  indicator: EndpointIndicator;
  tooltip: string;
} {
  // Runtime state takes priority — these are active operations
  if (endpoint.runtimeState === RuntimeState.Installing) {
    return { indicator: 'installing', tooltip: 'Installing from library...' };
  }
  if (endpoint.runtimeState === RuntimeState.SettingUp) {
    return { indicator: 'setting-up', tooltip: 'Running setup...' };
  }
  if (endpoint.runtimeState === RuntimeState.Initializing) {
    return { indicator: 'initializing', tooltip: 'Loading endpoint...' };
  }

  const setup = endpoint.setupStatus;

  // Has setup.yaml with incomplete steps
  if (setup != null && !setup.isComplete) {
    const pending = setup.pendingSteps?.length ?? 0;
    return {
      indicator: 'setup-incomplete',
      tooltip: `Setup incomplete (${setup.completed}/${setup.totalSteps} steps done, ${pending} pending)`,
    };
  }

  // Enabled = ready to use
  if (endpoint.enabled) {
    return { indicator: 'ready', tooltip: 'Ready' };
  }

  // Disabled
  return { indicator: 'disabled', tooltip: 'Disabled' };
}

// Endpoint list item - Single row layout for better scannability
function EndpointItem({
  endpoint,
  isSelected,
  onClick,
}: {
  endpoint: EndpointInfo;
  isSelected: boolean;
  onClick: () => void;
}) {
  const colors = typeColors[endpoint.type] || { bg: 'bg-secondary/20', text: 'text-muted-foreground' };
  const status = getEndpointStatus(endpoint);

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
        isSelected
          ? 'bg-primary/10 border border-primary/20'
          : 'hover:bg-secondary/50 border border-transparent'
      }`}
    >
      <div className="flex items-center gap-2">
        {/* TODO(AGENT_ONLY): Type badge hidden — all endpoints are agents now.
            To restore, uncomment the <span> below. */}
        {/* <span
          className={`text-[11px] font-medium py-0.5 rounded-md flex-shrink-0 w-12 text-center ${colors.bg} ${colors.text}`}
        >
          {typeLabelsShort[endpoint.type] ?? endpoint.type}
        </span> */}

        {/* Name - primary content */}
        <span className={`text-sm font-medium truncate flex-1 ${
          status.indicator === 'ready' ? 'text-foreground' : 'text-muted-foreground'
        }`}>
          {endpoint.name || endpoint.slug}
        </span>

        {/* Policies indicator */}
        {endpoint.hasPolicies && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="flex-shrink-0 text-chart-3">
                <ShieldCheck className="w-3.5 h-3.5" />
              </span>
            </TooltipTrigger>
            <TooltipContent side="right">
              <p>Has policies</p>
            </TooltipContent>
          </Tooltip>
        )}

        {/* Status indicator */}
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="flex-shrink-0">
              {renderStatusIcon(status.indicator)}
            </span>
          </TooltipTrigger>
          <TooltipContent side="right">
            <p>{status.tooltip}</p>
          </TooltipContent>
        </Tooltip>
      </div>
    </button>
  );
}

export function Sidebar({ onSettingsClick }: SidebarProps) {
  const { endpoints, selectedEndpointSlug, selectEndpoint, isInitializing, setCreateDialogOpen, showLibrary, setShowLibrary } = useAppStore();

  // Local filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all');

  // Filter endpoints based on search and type
  const filteredEndpoints = useMemo(() => {
    if (!endpoints) return [];
    return endpoints.filter((ep) => {
      // Search filter
      const matchesSearch =
        !searchQuery ||
        ep.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        ep.slug.toLowerCase().includes(searchQuery.toLowerCase());

      // Type filter
      const matchesType = typeFilter === 'all' || ep.type === typeFilter;

      return matchesSearch && matchesType;
    });
  }, [endpoints, searchQuery, typeFilter]);

  const handleEndpointClick = (slug: string) => {
    selectEndpoint(slug);
  };

  const clearFilters = () => {
    setSearchQuery('');
    setTypeFilter('all');
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header: search + filter + create */}
      <div className="px-3 pt-3 pb-3 flex-shrink-0">
        <div className="flex items-center gap-1.5">
          <div className="flex-1">
            <SearchInput value={searchQuery} onChange={setSearchQuery} />
          </div>
          {/* TODO(AGENT_ONLY): Type filter hidden — only agent endpoints shown.
              To restore, uncomment: <FilterButton selected={typeFilter} onChange={setTypeFilter} /> */}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => setCreateDialogOpen(true)}
                className="
                  flex-shrink-0 w-9 h-9 flex items-center justify-center
                  rounded-lg border border-border
                  bg-card/50 hover:bg-secondary/50
                  text-muted-foreground hover:text-foreground
                  transition-colors duration-150
                  focus:outline-none focus:ring-2 focus:ring-ring/30
                "
                aria-label="Create new endpoint"
              >
                <Plus className="w-5 h-5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <p>Create Endpoint</p>
            </TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Endpoints list - scrollable */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {isInitializing ? (
          <SidebarSkeleton />
        ) : endpoints.length === 0 ? (
          <div className="text-center py-8 px-4">
            <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-secondary/50 flex items-center justify-center">
              <FolderOpen className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium text-foreground mb-1">No endpoints yet</p>
            <p className="text-xs text-muted-foreground mb-4">Create your first endpoint to get started</p>
            <button
              onClick={() => setCreateDialogOpen(true)}
              className="
                inline-flex items-center gap-2 px-4 py-2
                bg-primary hover:bg-primary/90
                text-primary-foreground text-sm font-medium
                rounded-lg transition-colors
                focus:outline-none focus:ring-2 focus:ring-ring/50
              "
            >
              <Plus className="w-4 h-4" />
              Create Endpoint
            </button>
          </div>
        ) : filteredEndpoints.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p className="text-sm">No matching endpoints</p>
            <button
              onClick={clearFilters}
              className="text-xs mt-2 text-primary hover:text-primary/80 transition-colors"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <div className="space-y-1">
            {filteredEndpoints.map((endpoint) => (
              <EndpointItem
                key={endpoint.slug}
                endpoint={endpoint}
                isSelected={selectedEndpointSlug === endpoint.slug}
                onClick={() => handleEndpointClick(endpoint.slug)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Library button */}
      <div className="px-2 pb-1 flex-shrink-0">
        <button
          onClick={() => setShowLibrary(!showLibrary)}
          className={`
            w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium
            transition-colors duration-150
            ${showLibrary
              ? 'bg-primary/10 text-primary border border-primary/20'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50 border border-transparent'
            }
          `}
        >
          <Store className="w-4 h-4 flex-shrink-0" />
          Library
        </button>
      </div>

      {/* Footer with status and settings */}
      <div className="px-3 py-2.5 border-t border-sidebar-border flex items-center justify-between flex-shrink-0">
        <StatusChip />
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={onSettingsClick}
              className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-colors"
            >
              <Settings className="w-4 h-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">
            <p>Settings</p>
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
