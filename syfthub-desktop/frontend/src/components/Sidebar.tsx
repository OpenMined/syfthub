import { useState, useMemo } from 'react';
import { Search, Settings, FolderOpen, Plus, ShieldCheck } from 'lucide-react';
import { useAppStore, type EndpointInfo } from '../stores/appStore';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { OpenMinedIcon } from '@/components/ui/openmined-icon';

// Filter type for endpoints
type TypeFilter = 'all' | 'model' | 'data_source';

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
        placeholder="Search endpoints..."
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

// Filter chips component
function FilterChips({
  selected,
  onChange,
}: {
  selected: TypeFilter;
  onChange: (filter: TypeFilter) => void;
}) {
  const filters: { value: TypeFilter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'model', label: 'Models' },
    { value: 'data_source', label: 'Sources' },
  ];

  return (
    <div className="flex gap-2">
      {filters.map((filter) => (
        <button
          key={filter.value}
          onClick={() => onChange(filter.value)}
          className={`
            px-3 py-1 text-xs font-medium rounded-full
            transition-all duration-150
            ${
              selected === filter.value
                ? 'bg-secondary text-foreground'
                : 'bg-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/50'
            }
          `}
        >
          {filter.label}
        </button>
      ))}
    </div>
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
};

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
        {/* Type badge - first for immediate categorization */}
        <span
          className={`text-[11px] font-medium px-1.5 py-0.5 rounded-md flex-shrink-0 ${colors.bg} ${colors.text}`}
        >
          {endpoint.type === 'data_source' ? 'Source' : 'Model'}
        </span>

        {/* Name - primary content */}
        <span className="text-sm font-medium truncate flex-1 text-foreground">
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

        {/* Enabled status indicator - last, clear semantic */}
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            endpoint.enabled ? 'bg-chart-2' : 'bg-muted-foreground/50'
          }`}
        />
      </div>
    </button>
  );
}

export function Sidebar({ onSettingsClick }: SidebarProps) {
  const { endpoints, selectedEndpointSlug, selectEndpoint, isInitializing, setCreateDialogOpen } = useAppStore();

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
      {/* Brand row */}
      <div className="px-3 pb-2 flex items-center gap-2 flex-shrink-0">
        <OpenMinedIcon className="w-5 h-5" />
        <span className="text-xs font-semibold text-sidebar-foreground tracking-wide">SyftHub</span>
      </div>

      {/* Header with search, create button, and filters */}
      <div className="px-3 pb-3 space-y-3 flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <SearchInput value={searchQuery} onChange={setSearchQuery} />
          </div>
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
        <FilterChips selected={typeFilter} onChange={setTypeFilter} />
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
