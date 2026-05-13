import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { updater } from '../../wailsjs/go/models';
import {
  CheckForUpdatesNow,
  GetUpdateState,
  SetAutoCheckEnabled,
  OpenReleaseNotes,
  DownloadUpdate,
  CancelDownload,
  RevealDownloadedUpdate,
  InstallUpdate,
} from '../../wailsjs/go/main/App';
import { EventsOn } from '../../wailsjs/runtime/runtime';

type UpdateState = updater.State;
type DownloadState = updater.DownloadState;
type InstallState = updater.InstallState;

interface UpdateContextValue {
  state: UpdateState | null;
  download: DownloadState | null;
  install: InstallState | null;
  /** Manually dismissed banner version. Resets when a new latest_version arrives. */
  dismissedVersion: string | null;
  /** True when the platform supports in-place install (Linux/Windows). */
  inPlaceInstallSupported: boolean;
  dismissBanner: () => void;
  checkNow: () => Promise<void>;
  setAutoCheck: (enabled: boolean) => Promise<void>;
  openReleaseNotes: (url: string) => Promise<void>;
  downloadUpdate: () => Promise<void>;
  cancelDownload: () => Promise<void>;
  revealDownload: (localPath: string) => Promise<void>;
  installUpdate: () => Promise<void>;
}

const UpdateContext = createContext<UpdateContextValue | null>(null);

interface UpdateProviderProps {
  children: ReactNode;
}

const idleDownload: DownloadState = { stage: 'idle' } as DownloadState;
const idleInstall: InstallState = { stage: 'idle' } as InstallState;

export function UpdateProvider({ children }: UpdateProviderProps) {
  const [state, setState] = useState<UpdateState | null>(null);
  const [download, setDownload] = useState<DownloadState | null>(idleDownload);
  const [install, setInstall] = useState<InstallState | null>(idleInstall);
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(null);

  // Initial fetch + event subscription. EventsOn returns a per-listener
  // unsubscribe function — use it (not EventsOff) so StrictMode's double
  // mount doesn't tear down a listener the still-mounted instance owns.
  useEffect(() => {
    let cancelled = false;
    GetUpdateState().then((s) => {
      if (!cancelled) setState(s);
    }).catch(() => { /* ignore — Go may not be ready */ });

    const offState = EventsOn('update:state', (payload: UpdateState) => setState(payload));
    const offDownload = EventsOn('update:download', (payload: DownloadState) => setDownload(payload));
    const offInstall = EventsOn('update:install', (payload: InstallState) => setInstall(payload));

    return () => {
      cancelled = true;
      offState();
      offDownload();
      offInstall();
    };
  }, []);

  // If a new latest_version arrives, clear stale banner dismissal AND
  // any download state that no longer applies (e.g., previous version
  // was downloaded but the latest just moved).
  useEffect(() => {
    if (!state) return;
    if (state.latest_version && dismissedVersion && state.latest_version !== dismissedVersion) {
      setDismissedVersion(null);
    }
    if (download && download.version && state.latest_version && download.version !== state.latest_version) {
      setDownload(idleDownload);
    }
  }, [state?.latest_version]);

  const dismissBanner = useCallback(() => {
    if (state?.latest_version) {
      setDismissedVersion(state.latest_version);
    }
  }, [state?.latest_version]);

  const checkNow = useCallback(async () => {
    await CheckForUpdatesNow();
  }, []);

  const setAutoCheck = useCallback(async (enabled: boolean) => {
    await SetAutoCheckEnabled(enabled);
  }, []);

  const openReleaseNotes = useCallback(async (url: string) => {
    await OpenReleaseNotes(url);
  }, []);

  const downloadUpdate = useCallback(async () => {
    await DownloadUpdate();
  }, []);

  const cancelDownload = useCallback(async () => {
    await CancelDownload();
    // The Go side doesn't emit a "cancelled" state explicitly; reset locally.
    setDownload(idleDownload);
  }, []);

  const revealDownload = useCallback(async (localPath: string) => {
    await RevealDownloadedUpdate(localPath);
  }, []);

  const installUpdate = useCallback(async () => {
    await InstallUpdate();
  }, []);

  // In-place install is supported on Linux + Windows only. Detect from
  // the manifest platform string.
  const inPlaceInstallSupported = state?.platform === 'linux/amd64' || state?.platform === 'windows/amd64';

  return (
    <UpdateContext.Provider value={{
      state,
      download,
      install,
      dismissedVersion,
      inPlaceInstallSupported,
      dismissBanner,
      checkNow,
      setAutoCheck,
      openReleaseNotes,
      downloadUpdate,
      cancelDownload,
      revealDownload,
      installUpdate,
    }}>
      {children}
    </UpdateContext.Provider>
  );
}

export function useUpdate() {
  const ctx = useContext(UpdateContext);
  if (!ctx) {
    throw new Error('useUpdate must be used within an UpdateProvider');
  }
  return ctx;
}

/** Whether the current state should block the entire app UI. */
export function isBlockingStage(state: UpdateState | null): boolean {
  return state?.stage === 'must_update';
}

/** Whether the notify banner should be shown for the current state. */
export function shouldShowBanner(state: UpdateState | null, dismissedVersion: string | null): boolean {
  if (!state) return false;
  if (state.stage !== 'available' && state.stage !== 'offline_grace') return false;
  if (!state.latest_version) return false;
  return state.latest_version !== dismissedVersion;
}

/** Per-platform install instructions surfaced in the assisted-download UI. */
export function platformInstructions(platform?: string): string {
  switch (platform) {
    case 'linux/amd64':
      return 'Linux: make the binary executable (chmod +x) and run it. Optionally move it into your PATH.';
    case 'windows/amd64':
      return 'Windows: just run the .exe — SmartScreen may warn on first launch; click "More info" → "Run anyway".';
    case 'darwin/arm64':
      return 'macOS: extract the .zip, drag SyftHub Desktop.app to /Applications. First launch: right-click → Open to bypass Gatekeeper.';
    default:
      return 'See the release page for install instructions.';
  }
}
