import { useAppStore } from '../stores/appStore';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { CodeTab } from './tabs/CodeTab';
import { DocsTab } from './tabs/DocsTab';
import { SettingsTab } from './tabs/SettingsTab';
import { LogsTab } from './tabs/LogsTab';

// Empty state when no endpoint is selected
function EmptyState() {
  return (
    <div className="h-full flex flex-col text-muted-foreground">
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <svg
            className="w-16 h-16 mx-auto mb-4 opacity-30"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
            />
          </svg>
          <h3 className="text-lg font-medium text-foreground mb-1">No Endpoint Selected</h3>
          <p className="text-sm">Select an endpoint from the sidebar to view details</p>
        </div>
      </div>
    </div>
  );
}

// Loading state
function LoadingState() {
  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-secondary border-t-primary rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">Loading endpoint...</p>
        </div>
      </div>
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
    setActiveTab,
    toggleEnabled,
  } = useAppStore();

  // No endpoint selected
  if (!selectedEndpointSlug) {
    return <EmptyState />;
  }

  // Loading endpoint
  if (isLoading && !selectedEndpointDetail) {
    return <LoadingState />;
  }

  // Endpoint not found
  if (!selectedEndpointDetail) {
    return (
      <div className="h-full flex flex-col text-destructive">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-lg font-medium">Endpoint Not Found</p>
            <p className="text-sm mt-1 text-muted-foreground">Could not load "{selectedEndpointSlug}"</p>
          </div>
        </div>
      </div>
    );
  }

  const detail = selectedEndpointDetail;

  return (
    <Tabs
      value={activeTab}
      onValueChange={(v) => setActiveTab(v as typeof activeTab)}
      className="h-full flex flex-col"
    >
      {/* Single-line header: Name | Tabs (centered) | Toggle */}
      <div className="flex-shrink-0 h-11 px-4 border-b border-border/50 bg-card/30 flex items-center">
        {/* Left: Name */}
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-medium text-foreground truncate">
            {detail.name || detail.slug}
          </h1>
        </div>

        {/* Center: Tabs */}
        <TabsList className="h-7 bg-transparent p-0 gap-1">
          <TabsTrigger
            value="settings"
            className="h-7 px-3 text-xs data-[state=active]:bg-secondary data-[state=active]:text-foreground rounded"
          >
            Settings
          </TabsTrigger>
          <TabsTrigger
            value="code"
            className="h-7 px-3 text-xs data-[state=active]:bg-secondary data-[state=active]:text-foreground rounded"
          >
            Code
          </TabsTrigger>
          <TabsTrigger
            value="docs"
            className="h-7 px-3 text-xs data-[state=active]:bg-secondary data-[state=active]:text-foreground rounded"
          >
            Docs
          </TabsTrigger>
          <TabsTrigger
            value="logs"
            className="h-7 px-3 text-xs data-[state=active]:bg-secondary data-[state=active]:text-foreground rounded"
          >
            Logs
          </TabsTrigger>
        </TabsList>

        {/* Right: Enable toggle */}
        <div className="flex-1 flex justify-end">
          <div className="flex items-center gap-2">
            <Switch
              checked={detail.enabled}
              onCheckedChange={() => toggleEnabled()}
              disabled={isSaving}
              className="data-[state=checked]:bg-chart-2 h-5 w-9"
            />
            <span className="text-xs text-muted-foreground w-14">
              {detail.enabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>
        </div>
      </div>

      {/* Tab content - full height */}
      <div className="flex-1 overflow-hidden">
        <TabsContent value="settings" className="h-full m-0 data-[state=active]:flex data-[state=active]:flex-col">
          <SettingsTab />
        </TabsContent>
        <TabsContent value="code" className="h-full m-0 data-[state=active]:flex data-[state=active]:flex-col">
          <CodeTab />
        </TabsContent>
        <TabsContent value="docs" className="h-full m-0 data-[state=active]:flex data-[state=active]:flex-col">
          <DocsTab />
        </TabsContent>
        <TabsContent value="logs" className="h-full m-0 data-[state=active]:flex data-[state=active]:flex-col">
          <LogsTab />
        </TabsContent>
      </div>
    </Tabs>
  );
}
