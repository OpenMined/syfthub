import { useEffect, ReactNode } from 'react';
import { useAppStore } from '../stores/appStore';
import { CreateEndpointDialog } from './CreateEndpointDialog';
import { DeleteEndpointDialog } from './DeleteEndpointDialog';
import { ChatView } from './ChatView';
import { WindowMinimise, WindowToggleMaximise, Quit } from '../../wailsjs/runtime/runtime';

interface AppShellProps {
  sidebar: ReactNode;
  children: ReactNode;
}

export function AppShell({ sidebar, children }: AppShellProps) {
  const { error, refreshAll, clearError, mainView, setMainView } = useAppStore();

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
      {/* Custom title bar */}
      <div className="wails-drag h-9 flex-shrink-0 border-b border-border/30 bg-card/30 flex items-center px-3">
        {/* Left spacer for centering */}
        <div className="w-32" />

        {/* Center: Navigation tabs */}
        <div className="flex-1 flex items-center justify-center">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setMainView('endpoints')}
              className={`h-5 px-3 text-xs rounded transition-colors duration-150 ${
                mainView === 'endpoints'
                  ? 'bg-secondary text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Endpoints
            </button>
            <button
              onClick={() => setMainView('chat')}
              className={`h-5 px-3 text-xs rounded transition-colors duration-150 ${
                mainView === 'chat'
                  ? 'bg-secondary text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              Chat
            </button>
          </div>
        </div>

        {/* Right: Window controls */}
        <div className="flex items-center gap-1.5 w-32 justify-end">
          <button
            onClick={WindowMinimise}
            className="w-3 h-3 rounded-full bg-[#f5bf4f] hover:brightness-110 transition-all"
            title="Minimize"
          />
          <button
            onClick={WindowToggleMaximise}
            className="w-3 h-3 rounded-full bg-[#5bbf45] hover:brightness-110 transition-all"
            title="Maximize"
          />
          <button
            onClick={Quit}
            className="w-3 h-3 rounded-full bg-[#ed6a5e] hover:brightness-110 transition-all"
            title="Close"
          />
        </div>
      </div>

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
      {mainView === 'endpoints' ? (
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar */}
          <aside className="w-64 flex-shrink-0 border-r border-sidebar-border bg-sidebar">
            {sidebar}
          </aside>

          {/* Content area */}
          <main className="flex-1 overflow-y-auto bg-background">
            {children}
          </main>
        </div>
      ) : (
        <div className="flex-1 overflow-hidden bg-background">
          <ChatView />
        </div>
      )}

      {/* Dialogs */}
      <CreateEndpointDialog />
      <DeleteEndpointDialog />
    </div>
  );
}
