import { useState, useEffect } from 'react';
import { useSettings } from './contexts/SettingsContext';
import { useAppStore } from './stores/appStore';
import { OnboardingWizard } from '@/components/OnboardingWizard';
import { SettingsModal } from '@/components/SettingsModal';
import { AppShell } from '@/components/AppShell';
import { Sidebar } from '@/components/Sidebar';
import { EndpointDetail } from '@/components/EndpointDetail';

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

  // Show loading spinner while checking settings
  if (isLoading) {
    return <LoadingSpinner />;
  }

  // Show onboarding wizard if not configured
  if (!isConfigured) {
    return <OnboardingWizard />;
  }

  // Show main dashboard
  return <Dashboard />;
}

export default App;
