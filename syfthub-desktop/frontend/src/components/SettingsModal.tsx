import { useState, useEffect } from 'react';
import { Info, Plug, RefreshCw, Settings2, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { useSettings } from '@/contexts/SettingsContext';
import { useUpdate } from '@/contexts/UpdateContext';
import { extractErrorMessage, isValidUrl } from '@/lib/utils';
import { BrowseForFolder, SetContainerEnabled, Stop, GetVersion } from '../../wailsjs/go/main/App';
import { Quit } from '../../wailsjs/runtime/runtime';
import { ErrorBanner } from '@/components/ui/error-banner';
import { Spinner } from '@/components/ui/spinner';
import { McpServersSection } from '@/components/tabs/McpServersSection';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

interface SettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type SettingsPage = 'general' | 'mcp' | 'about';

const PAGES: { id: SettingsPage; label: string; icon: LucideIcon }[] = [
  { id: 'general', label: 'General', icon: Settings2 },
  { id: 'mcp', label: 'MCP Servers', icon: Plug },
  { id: 'about', label: 'About', icon: Info },
];

function updateStageLabel(stage: string, latestVersion?: string): string {
  switch (stage) {
    case 'idle': return 'Up to date';
    case 'checking': return 'Checking…';
    case 'available': return `v${latestVersion} available`;
    case 'must_update': return `Update required (v${latestVersion})`;
    case 'offline_grace':
    case 'offline_no_grace': return "Couldn't reach update server";
    case 'unsupported_platform': return 'Platform not supported';
    default: return stage;
  }
}

export function SettingsModal({ open, onOpenChange }: SettingsModalProps) {
  const { settings, saveSettings, defaultEndpointsPath, refreshSettings } = useSettings();
  const { state: updateState, checkNow, setAutoCheck } = useUpdate();

  const [page, setPage] = useState<SettingsPage>('general');
  const [syfthubUrl, setSyfthubUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [endpointsPath, setEndpointsPath] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingContainerEnabled, setPendingContainerEnabled] = useState<boolean | null>(null);
  const [isRestarting, setIsRestarting] = useState(false);
  const [restartStatus, setRestartStatus] = useState<string>('');
  const [version, setVersion] = useState<string>('');
  const [isChecking, setIsChecking] = useState(false);

  // Pull the version once per open so the About page can render it.
  useEffect(() => {
    if (open) {
      GetVersion().then(setVersion).catch(() => setVersion(''));
    }
  }, [open]);

  // Initialize the connection draft with current settings when the modal opens.
  useEffect(() => {
    if (open && settings) {
      setPage('general');
      setSyfthubUrl(settings.hub_url || '');
      setApiKey(settings.api_token || '');
      setEndpointsPath(settings.endpoints_path || defaultEndpointsPath || '');
    }
  }, [open, settings, defaultEndpointsPath]);

  const handleBrowse = async () => {
    const path = await BrowseForFolder('Select Endpoints Directory');
    if (path) {
      setEndpointsPath(path);
    }
  };

  const handleSave = async () => {
    if (!isValidUrl(syfthubUrl)) {
      setError('Please enter a valid URL');
      return;
    }
    if (!endpointsPath) {
      setError('Please specify an endpoints directory');
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await saveSettings(syfthubUrl, apiKey, endpointsPath);
      await refreshSettings();
      onOpenChange(false);
    } catch (err) {
      setError(extractErrorMessage(err, 'Failed to save settings'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleClose = () => {
    setError(null);
    onOpenChange(false);
  };

  const isUrlValid = !syfthubUrl || isValidUrl(syfthubUrl);
  // The General page is a draft that applies on Save; everything else applies
  // immediately. The dot on the nav item flags an unsaved draft when the user
  // wanders to another page.
  const dirty =
    !!settings &&
    (syfthubUrl !== (settings.hub_url || '') ||
      apiKey !== (settings.api_token || '') ||
      endpointsPath !== (settings.endpoints_path || defaultEndpointsPath || ''));

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[480px] max-h-[85vh] overflow-hidden p-0 gap-0 sm:max-w-[640px]">
        {/* Nav rail */}
        <nav className="flex w-44 shrink-0 flex-col gap-0.5 border-r border-border/60 bg-muted/30 p-3">
          <DialogTitle className="px-2.5 pb-3 pt-1 text-sm font-semibold">Settings</DialogTitle>
          <DialogDescription className="sr-only">
            Configure your SyftHub Desktop connection, MCP servers, and updates
          </DialogDescription>
          {PAGES.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setPage(id)}
              className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors ${
                page === id
                  ? 'bg-accent text-foreground font-medium'
                  : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1 text-left">{label}</span>
              {id === 'general' && dirty && (
                <span className="h-1.5 w-1.5 rounded-full bg-warning" aria-label="Unsaved changes" />
              )}
            </button>
          ))}
        </nav>

        {/* Page */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex-1 overflow-y-auto px-6 py-5">
            {page === 'general' && (
              <div className="space-y-5">
                <PageHeader title="General" description="Connection, storage, and runtime." />

                <div className="space-y-2">
                  <Label htmlFor="settings-syfthubUrl">SyftHub URL</Label>
                  <Input
                    id="settings-syfthubUrl"
                    type="url"
                    value={syfthubUrl}
                    onChange={(e) => setSyfthubUrl(e.target.value)}
                    placeholder="https://syfthub-dev.openmined.org"
                    className={!isUrlValid ? 'border-destructive focus:border-destructive' : ''}
                  />
                  {!isUrlValid && (
                    <p className="text-xs text-destructive">Please enter a valid URL</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="settings-apiKey">
                    API Key <span className="text-xs font-normal text-muted-foreground">(optional)</span>
                  </Label>
                  <Input
                    id="settings-apiKey"
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Enter your API key"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="settings-endpointsPath">Endpoints Directory</Label>
                  <div className="flex gap-2">
                    <Input
                      id="settings-endpointsPath"
                      type="text"
                      value={endpointsPath}
                      onChange={(e) => setEndpointsPath(e.target.value)}
                      placeholder={defaultEndpointsPath || '.endpoints'}
                      className="flex-1"
                    />
                    <Button type="button" variant="outline" onClick={handleBrowse}>
                      Browse
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Changing this will require reloading endpoints
                  </p>
                </div>

                <div className="flex items-center justify-between border-t border-border/60 pt-5">
                  <div className="space-y-0.5 pr-4">
                    <Label>Container Mode</Label>
                    <p className="text-xs text-muted-foreground">
                      Run endpoints in Docker/Podman containers. Applies after restart.
                    </p>
                  </div>
                  <Switch
                    checked={settings?.container_enabled ?? false}
                    onCheckedChange={(checked) => {
                      setError(null);
                      setPendingContainerEnabled(checked);
                    }}
                  />
                </div>
              </div>
            )}

            {page === 'mcp' && <McpServersSection />}

            {page === 'about' && (
              <div className="space-y-5">
                <PageHeader title="About" description="Version and update preferences." />

                <div className="divide-y divide-border/60 text-sm">
                  <div className="flex items-center justify-between py-2.5">
                    <span className="text-muted-foreground">Version</span>
                    <span className="font-mono text-xs">{version || '—'}</span>
                  </div>
                  {updateState && updateState.stage !== 'disabled' && (
                    <>
                      <div className="flex items-center justify-between py-2.5">
                        <span className="text-muted-foreground">Status</span>
                        <span className="text-xs">
                          {updateStageLabel(updateState.stage, updateState.latest_version)}
                        </span>
                      </div>
                      {updateState.last_checked_at && (
                        <div className="flex items-center justify-between py-2.5">
                          <span className="text-muted-foreground">Last checked</span>
                          <span className="text-xs">
                            {new Date(updateState.last_checked_at).toLocaleString()}
                          </span>
                        </div>
                      )}
                      <div className="flex items-center justify-between py-2.5">
                        <Label htmlFor="settings-autoCheck" className="cursor-pointer font-normal text-muted-foreground">
                          Automatic update checks
                        </Label>
                        <Switch
                          id="settings-autoCheck"
                          checked={updateState.auto_check_enabled ?? true}
                          onCheckedChange={async (checked) => {
                            try {
                              await setAutoCheck(checked);
                            } catch (err) {
                              setError(extractErrorMessage(err, 'Failed to update preference'));
                            }
                          }}
                        />
                      </div>
                    </>
                  )}
                </div>

                {updateState && updateState.stage !== 'disabled' && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={async () => {
                      setIsChecking(true);
                      try {
                        await checkNow();
                        // Give the background goroutine a moment to publish.
                        await new Promise((r) => setTimeout(r, 600));
                      } finally {
                        setIsChecking(false);
                      }
                    }}
                    disabled={isChecking || updateState.stage === 'checking'}
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${isChecking ? 'animate-spin' : ''}`} />
                    {isChecking ? 'Checking…' : 'Check for updates'}
                  </Button>
                )}
                {updateState?.stage === 'disabled' && (
                  <p className="text-xs text-muted-foreground">
                    Auto-update is disabled for this build (development version or bypass environment variable set).
                  </p>
                )}
              </div>
            )}
          </div>

          {error && (
            <div className="px-6 pb-3">
              <ErrorBanner message={error} />
            </div>
          )}

          <footer className="flex justify-end gap-2 border-t border-border/60 px-6 py-3.5">
            {page === 'general' ? (
              <>
                <Button variant="outline" onClick={handleClose} disabled={isSaving}>
                  Cancel
                </Button>
                <Button onClick={handleSave} disabled={isSaving || !dirty}>
                  {isSaving ? 'Saving…' : 'Save Changes'}
                </Button>
              </>
            ) : (
              <Button variant="outline" onClick={handleClose}>
                Close
              </Button>
            )}
          </footer>
        </div>
      </DialogContent>
    </Dialog>

    <AlertDialog open={pendingContainerEnabled !== null}>
      <AlertDialogContent onEscapeKeyDown={(e) => e.preventDefault()}>
        {isRestarting ? (
          <>
            <AlertDialogHeader>
              <AlertDialogTitle>Restarting SyftHub Desktop</AlertDialogTitle>
              <AlertDialogDescription>
                Please don't close the window — this can take up to 15 seconds
                while running containers are stopped cleanly.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="flex items-center gap-3 rounded-md border bg-muted/40 px-3 py-3 text-sm">
              <Spinner className="h-4 w-4 text-foreground" />
              <span className="text-foreground">{restartStatus}</span>
            </div>
          </>
        ) : (
          <>
            <AlertDialogHeader>
              <AlertDialogTitle>Restart required</AlertDialogTitle>
              <AlertDialogDescription>
                {pendingContainerEnabled ? 'Enabling' : 'Disabling'} Container Mode
                requires restarting SyftHub Desktop to take effect. The app will
                close now — please reopen it to continue.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel onClick={() => setPendingContainerEnabled(null)}>
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={async (e) => {
                  e.preventDefault();
                  if (pendingContainerEnabled === null) return;
                  setIsRestarting(true);
                  try {
                    setRestartStatus('Saving configuration…');
                    await SetContainerEnabled(pendingContainerEnabled);
                    setRestartStatus(
                      pendingContainerEnabled
                        ? 'Shutting down current endpoints…'
                        : 'Stopping running containers…',
                    );
                    await Stop();
                    setRestartStatus('Closing app…');
                    Quit();
                  } catch (err) {
                    setIsRestarting(false);
                    setRestartStatus('');
                    setPendingContainerEnabled(null);
                    setError(extractErrorMessage(err, 'Failed to toggle container mode'));
                  }
                }}
              >
                Restart
              </AlertDialogAction>
            </AlertDialogFooter>
          </>
        )}
      </AlertDialogContent>
    </AlertDialog>
    </>
  );
}

function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <header>
      <h3 className="text-base font-semibold text-foreground">{title}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
    </header>
  );
}
