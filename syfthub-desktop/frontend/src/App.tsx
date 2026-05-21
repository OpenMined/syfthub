import { useState, useEffect } from 'react';
import { useSettings } from './contexts/SettingsContext';
import { useAppStore } from './stores/appStore';
import { OnboardingWizard } from '@/components/OnboardingWizard';
import { SettingsModal } from '@/components/SettingsModal';
import { AppShell } from '@/components/AppShell';
import { Sidebar } from '@/components/Sidebar';
import { EndpointDetail } from '@/components/EndpointDetail';
import { MustUpdateModal } from '@/components/MustUpdateModal';
import { InstallProgress } from '@/components/InstallProgress';
import { LoadProgress } from '@/components/LoadProgress';

// Loading spinner
function LoadingSpinner() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-card to-background flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-secondary border-t-primary rounded-full animate-spin mx-auto mb-4" />
        <p className="text-muted-foreground">Loading...</p>
      </div>
    </div>
  );
}

// Main Dashboard component with new layout
function Dashboard() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const initialize = useAppStore((state) => state.initialize);

  // Auto-initialize app state on mount
  useEffect(() => {
    initialize();
  }, [initialize]);

  return (
    <>
      <AppShell sidebar={<Sidebar onSettingsClick={() => setSettingsOpen(true)} />}>
        <EndpointDetail />
      </AppShell>

      {/* Settings Modal */}
      <SettingsModal open={settingsOpen} onOpenChange={setSettingsOpen} />
    </>
  );
}

function App() {
  const { isConfigured, isLoading } = useSettings();

  // The MustUpdateModal renders above all other state — onboarding,
  // dashboard, loading. A hard-gate is a hard-gate.
  let body: React.ReactNode;
  if (isLoading) {
    body = <LoadingSpinner />;
  } else if (!isConfigured) {
    body = <OnboardingWizard />;
  } else {
    body = <Dashboard />;
  }

  return (
    <>
      {body}
      <MustUpdateModal />
      <InstallProgress />
      <LoadProgress />
    </>
  );
}

export default App;
