import { useState, useEffect } from 'react';
import { Globe, KeyRound, FolderOpen, Container, RefreshCw, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import { useSettings } from '@/contexts/SettingsContext';
import { useUpdate } from '@/contexts/UpdateContext';
import { extractErrorMessage, isValidUrl } from '@/lib/utils';
import { BrowseForFolder, SetContainerEnabled, Stop, GetVersion } from '../../wailsjs/go/main/App';
import { Quit } from '../../wailsjs/runtime/runtime';
import { ErrorBanner } from '@/components/ui/error-banner';
import { Spinner } from '@/components/ui/spinner';
import {
  AlertDialog,
  AlertDialogAction,
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

  // Pull the version once per open so the About section can render it.
  useEffect(() => {
    if (open) {
      GetVersion().then(setVersion).catch(() => setVersion(''));
    }
  }, [open]);

  // Initialize form with current settings when modal opens
  useEffect(() => {
    if (open && settings) {
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

  const handleCancel = () => {
    setError(null);
    onOpenChange(false);
  };

  const isUrlValid = !syfthubUrl || isValidUrl(syfthubUrl);

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Configure your SyftHub Desktop connection and storage
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-4">
          {/* SyftHub URL */}
          <div className="space-y-2">
            <Label htmlFor="settings-syfthubUrl" className="flex items-center gap-1.5 text-foreground">
              <Globe className="w-4 h-4 text-muted-foreground" />
              SyftHub URL
            </Label>
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

          {/* API Key */}
          <div className="space-y-2">
            <Label htmlFor="settings-apiKey" className="flex items-center gap-1.5 text-foreground">
              <KeyRound className="w-4 h-4 text-muted-foreground" />
              API Key <span className="text-muted-foreground text-xs">(optional)</span>
            </Label>
            <Input
              id="settings-apiKey"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Enter your API key"
            />
          </div>

          {/* Endpoints Path */}
          <div className="space-y-2">
            <Label htmlFor="settings-endpointsPath" className="flex items-center gap-1.5 text-foreground">
              <FolderOpen className="w-4 h-4 text-muted-foreground" />
              Endpoints Directory
            </Label>
            <div className="flex gap-2">
              <Input
                id="settings-endpointsPath"
                type="text"
                value={endpointsPath}
                onChange={(e) => setEndpointsPath(e.target.value)}
                placeholder={defaultEndpointsPath || '.endpoints'}
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleBrowse}
              >
                Browse
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Changing this will require reloading endpoints
            </p>
          </div>

          {/* Container Mode */}
          <div className="flex items-center justify-between py-1">
            <div className="space-y-0.5">
              <Label className="flex items-center gap-1.5 text-foreground">
                <Container className="w-4 h-4 text-muted-foreground" />
                Container Mode
              </Label>
              <p className="text-xs text-muted-foreground">
                Run endpoints in Docker/Podman containers. Requires restart.
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

          {/* About & Updates */}
          <div className="space-y-2 pt-2 border-t border-border/60">
            <Label className="flex items-center gap-1.5 text-foreground">
              <Info className="w-4 h-4 text-muted-foreground" />
              About & Updates
            </Label>
            <div className="rounded-md border border-border/60 bg-muted/30 p-3 space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Version</span>
                <span className="font-mono text-xs text-foreground">{version || '—'}</span>
              </div>
              {updateState && updateState.stage !== 'disabled' && (
                <>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Status</span>
                    <span className="text-xs text-foreground">
                      {updateStageLabel(updateState.stage, updateState.latest_version)}
                    </span>
                  </div>
                  {updateState.last_checked_at && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Last checked</span>
                      <span className="text-xs text-foreground">
                        {new Date(updateState.last_checked_at).toLocaleString()}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <Label htmlFor="settings-autoCheck" className="text-muted-foreground cursor-pointer">
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
                    className="w-full"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 mr-2 ${isChecking ? 'animate-spin' : ''}`} />
                    {isChecking ? 'Checking…' : 'Check for updates now'}
                  </Button>
                </>
              )}
              {updateState?.stage === 'disabled' && (
                <p className="text-xs text-muted-foreground">
                  Auto-update is disabled for this build (development version or bypass environment variable set).
                </p>
              )}
            </div>
          </div>

          <ErrorBanner message={error} />

        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleCancel}
            disabled={isSaving}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={isSaving}
          >
            {isSaving ? 'Saving...' : 'Save Changes'}
          </Button>
        </DialogFooter>
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
