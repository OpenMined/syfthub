import { useAppStore } from '../stores/appStore';
import { Switch } from '@/components/ui/switch';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  OverviewSection,
  EnvironmentSection,
  DependenciesSection,
  PoliciesSection,
} from './tabs/SettingsTab';
import { CodeTab } from './tabs/CodeTab';
import { DocsTab } from './tabs/DocsTab';
import { LogsTab } from './tabs/LogsTab';

type Section =
  | 'overview'
  | 'environment'
  | 'dependencies'
  | 'policies'
  | 'code'
  | 'docs'
  | 'logs';

const NAV_GROUPS: { label: string; items: { id: Section; label: string }[] }[] = [
  {
    label: 'General',
    items: [
      { id: 'overview', label: 'Overview' },
      { id: 'docs', label: 'Docs' },
      { id: 'policies', label: 'Policies' },
    ],
  },
  {
    label: 'Monitor',
    items: [{ id: 'logs', label: 'Logs' }],
  },
  {
    label: 'Configure',
    items: [
      { id: 'environment', label: 'Environment' },
      { id: 'dependencies', label: 'Dependencies' },
      { id: 'code', label: 'Code' },
    ],
  },
];

function EmptyState() {
  return (
    <div className="h-full flex items-center justify-center text-muted-foreground">
      <div className="text-center">
        <svg
          className="w-10 h-10 mx-auto mb-3 opacity-30"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
          />
        </svg>
        <p className="text-sm">Select an endpoint from the sidebar</p>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="w-6 h-6 border-2 border-secondary border-t-primary rounded-full animate-spin" />
    </div>
  );
}

export function EndpointDetail() {
  const {
    selectedEndpointSlug,
    selectedEndpointDetail,
    isLoading,
    isSaving,
    activeTab,
    settingsSection,
    setActiveTab,
    setSettingsSection,
    toggleEnabled,
  } = useAppStore();

  if (!selectedEndpointSlug) return <EmptyState />;
  if (isLoading && !selectedEndpointDetail) return <LoadingState />;

  if (!selectedEndpointDetail) {
    return (
      <div className="h-full flex items-center justify-center text-destructive">
        <div className="text-center">
          <p className="text-sm font-medium">Endpoint Not Found</p>
          <p className="text-xs mt-1 text-muted-foreground">
            Could not load "{selectedEndpointSlug}"
          </p>
        </div>
      </div>
    );
  }

  const detail = selectedEndpointDetail;

  // Derive the active section from the existing two store fields. Skills is no
  // longer a standalone destination — it lives inside Overview now, so any
  // persisted 'skills' selection lands on Overview.
  const rawSection = activeTab === 'settings' ? settingsSection : activeTab;
  const section: Section =
    rawSection === 'skills' ? 'overview' : (rawSection as Section);

  const navigate = (s: Section) => {
    if (s === 'code' || s === 'docs' || s === 'logs') {
      setActiveTab(s);
    } else {
      setActiveTab('settings');
      setSettingsSection(s as typeof settingsSection);
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* ── Top bar: name + status only (32px) ───────────────────────────── */}
      <header className="flex-shrink-0 h-8 px-4 border-b border-border/50 flex items-center justify-between">
        <h1 className="text-sm font-medium text-foreground truncate min-w-0">
          {detail.name || detail.slug}
        </h1>
        <Tooltip>
          <TooltipTrigger asChild>
            <Switch
              checked={detail.enabled}
              onCheckedChange={() => toggleEnabled()}
              disabled={isSaving}
              aria-label={detail.enabled ? 'Disable endpoint' : 'Enable endpoint'}
              className="data-[state=checked]:bg-chart-2 h-4 w-7"
            />
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <p>{detail.enabled ? 'Enabled — click to disable' : 'Disabled — click to enable'}</p>
          </TooltipContent>
        </Tooltip>
      </header>

      {/* ── Body: unified left rail + content ────────────────────────────── */}
      <div className="flex-1 flex min-h-0">
        {/* Left rail */}
        <nav className="w-44 flex-shrink-0 border-r border-border/30 flex flex-col py-2 overflow-y-auto">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="mb-2">
              <div className="px-3 pb-1 pt-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
                {group.label}
              </div>
              <div className="px-1.5">
                {group.items.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => navigate(item.id)}
                    aria-current={section === item.id ? 'page' : undefined}
                    className={`w-full text-left px-2.5 py-1.5 text-sm rounded transition-colors ${
                      section === item.id
                        ? 'bg-secondary/60 text-foreground'
                        : 'text-muted-foreground hover:text-foreground hover:bg-card/40'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Section content */}
        <div className="flex-1 min-w-0 overflow-hidden flex flex-col">
          {section === 'overview' && <ScrollPane><OverviewSection /></ScrollPane>}
          {section === 'environment' && <ScrollPane><EnvironmentSection /></ScrollPane>}
          {section === 'dependencies' && <ScrollPane><DependenciesSection /></ScrollPane>}
          {section === 'policies' && <ScrollPane><PoliciesSection /></ScrollPane>}
          {section === 'code' && <CodeTab />}
          {section === 'docs' && <DocsTab />}
          {section === 'logs' && <LogsTab />}
        </div>
      </div>
    </div>
  );
}

// Settings-style sections render their own padding; just wrap in a scroll container.
function ScrollPane({ children }: { children: React.ReactNode }) {
  return <div className="flex-1 overflow-y-auto">{children}</div>;
}
