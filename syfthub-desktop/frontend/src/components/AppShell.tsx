import { useEffect, ReactNode } from 'react';
import { useAppStore } from '../stores/appStore';
import { CreateEndpointDialog } from './CreateEndpointDialog';
import { DeleteEndpointDialog } from './DeleteEndpointDialog';

interface AppShellProps {
  sidebar: ReactNode;
  children: ReactNode;
}

export function AppShell({ sidebar, children }: AppShellProps) {
  const { error, refreshAll, clearError } = useAppStore();

  // Initial data load
  useEffect(() => {
    refreshAll();

    // Poll status every 2 seconds
    const interval = setInterval(() => {
      useAppStore.getState().fetchStatus();
    }, 2000);

    return () => clearInterval(interval);
  }, [refreshAll]);

  return (
    <div className="h-screen flex flex-col bg-background text-foreground">
      {/* Error banner */}
      {error && (
        <div className="px-4 py-2 bg-destructive/10 border-b border-destructive/20 flex items-center justify-between flex-shrink-0">
          <p className="text-sm text-destructive">{error}</p>
          <button
            onClick={clearError}
            className="text-destructive hover:text-destructive/80 text-sm"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <aside className="w-64 flex-shrink-0 border-r border-border/50 bg-card/30">
          {sidebar}
        </aside>

        {/* Content area */}
        <main className="flex-1 overflow-y-auto bg-background">
          {children}
        </main>
      </div>

      {/* Dialogs */}
      <CreateEndpointDialog />
      <DeleteEndpointDialog />
    </div>
  );
}
