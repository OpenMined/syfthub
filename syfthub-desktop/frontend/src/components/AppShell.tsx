import { useEffect, ReactNode } from 'react';
import { useAppStore } from '../stores/appStore';
import { CreateEndpointDialog } from './CreateEndpointDialog';
import { DeleteEndpointDialog } from './DeleteEndpointDialog';
import { RenameEndpointDialog } from './RenameEndpointDialog';
import { SetupFlowDialog } from './SetupFlowDialog';
import { ChatView } from './ChatView';
import { LibraryView } from './LibraryView';
import { UpdateBanner } from './UpdateBanner';
import { WindowControls } from './ui/window-controls';

const isMac = navigator.userAgent.includes('Macintosh');

interface AppShellProps {
  sidebar: ReactNode;
  children: ReactNode;
}

export function AppShell({ sidebar, children }: AppShellProps) {
  const { error, refreshAll, clearError, mainView, setMainView, showLibrary } = useAppStore();

  // Initial data load
  useEffect(() => {
    refreshAll();

    // Poll status every 2 seconds
    const interval = setInterval(() => {
      useAppStore.getState().fetchStatus();
    }, 2000);

    return () => clearInterval(interval);
  }, [refreshAll]);

  const tabs = (
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
  );

  return (
    <div className={`h-screen flex flex-col bg-background text-foreground ${!isMac ? 'rounded-xl overflow-hidden shadow-2xl' : ''}`}>
      {isMac ? (
        /* macOS: transparent native title bar floats above; left pad reserves
           space for the traffic-light controls overlaid by the OS. */
        <div className="wails-drag h-9 flex-shrink-0 border-b border-border/30 bg-background flex items-center justify-center px-3 pl-[80px]">
          {tabs}
        </div>
      ) : (
        /* Windows / Linux: frameless window — draw our own controls. */
        <div className="wails-drag h-9 flex-shrink-0 border-b border-border/30 bg-card/30 flex items-center px-3">
          <WindowControls />
          <div className="flex-1 flex items-center justify-center">{tabs}</div>
          <div className="w-32" />
        </div>
      )}

      {/* Update banner — sits between nav bar and content, above the error banner */}
      <UpdateBanner />

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
      {mainView === 'endpoints' && (
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar */}
          <aside className="w-64 flex-shrink-0 border-r border-sidebar-border bg-sidebar">
            {sidebar}
          </aside>

          {/* Content area — library or endpoint detail */}
          <main className="flex-1 overflow-y-auto bg-background">
            {showLibrary ? <LibraryView /> : children}
          </main>
        </div>
      )}
      {mainView === 'chat' && (
        <div className="flex-1 overflow-hidden bg-background">
          <ChatView />
        </div>
      )}

      {/* Dialogs */}
      <CreateEndpointDialog />
      <DeleteEndpointDialog />
      <RenameEndpointDialog />
      <SetupFlowDialog />
    </div>
  );
}
