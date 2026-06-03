import { ShieldAlert, ExternalLink, Download, FolderOpen, RefreshCw } from 'lucide-react';
import { Quit } from '../../wailsjs/runtime/runtime';
import { useUpdate, isBlockingStage, platformInstructions } from '@/contexts/UpdateContext';
import { Button } from '@/components/ui/button';
import { formatBytes } from '@/lib/utils';

/**
 * MustUpdateModal is the hard-gate UI for the auto-updater.
 *
 * When the manifest's min_supported_version exceeds the currently
 * running version, this modal mounts as a full-screen blocking overlay.
 * The only actions offered are Quit and Download — there is deliberately
 * no "Continue at my own risk", since a dismissable security gate is
 * not a security gate.
 *
 * The Download button triggers an in-app artifact download with SHA-256
 * verification, then "Install & restart" performs the in-place swap and
 * relaunch on every shipped platform (Linux, Windows, and signed macOS).
 * Platforms without a one-click installer fall back to a manual
 * "Open downloaded file" step.
 */
export function MustUpdateModal() {
  const {
    state, download, inPlaceInstallSupported,
    openReleaseNotes, downloadUpdate, cancelDownload, revealDownload, installUpdate,
  } = useUpdate();

  if (!isBlockingStage(state) || !state) return null;

  const downloadActive =
    download?.stage === 'downloading' &&
    download.version === state.latest_version;
  const downloadReady =
    download?.stage === 'ready' &&
    download.version === state.latest_version &&
    !!download.local_path;
  const downloadFailed =
    download?.stage === 'failed' &&
    download.version === state.latest_version;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-background/95 backdrop-blur-sm"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="must-update-title"
    >
      <div className="max-w-md w-full mx-4 bg-card border border-destructive/40 rounded-lg shadow-2xl p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="rounded-full bg-destructive/15 p-2">
            <ShieldAlert className="w-6 h-6 text-destructive" />
          </div>
          <div>
            <h2 id="must-update-title" className="text-lg font-semibold text-foreground">
              Update required
            </h2>
            <p className="text-xs text-muted-foreground">
              You are running v{state.current_version}
            </p>
          </div>
        </div>

        <div className="text-sm text-foreground space-y-2">
          <p>
            A required update to <span className="font-medium">v{state.latest_version}</span> must be installed
            before SyftHub Desktop can continue.
          </p>
          {state.must_update_reason && (
            <p className="text-muted-foreground text-xs border-l-2 border-destructive/30 pl-2">
              {state.must_update_reason}
            </p>
          )}
          {!state.platform_supported && (
            <p className="text-muted-foreground text-xs">
              Your platform ({state.platform}) is not available as a pre-built binary —
              please visit the release page for source-build instructions.
            </p>
          )}
        </div>

        {/* Download status block */}
        {(downloadActive || downloadReady || downloadFailed) && (
          <div className="rounded-md border border-border/60 bg-muted/30 p-3 text-sm space-y-2">
            {downloadActive && (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-foreground">Downloading…</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {formatBytes(download?.bytes_done)} / {formatBytes(download?.bytes_total)}
                  </span>
                </div>
                <div className="h-1 bg-secondary rounded overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{
                      width: download?.bytes_total
                        ? `${Math.min(100, ((download.bytes_done ?? 0) / download.bytes_total) * 100)}%`
                        : '0%',
                    }}
                  />
                </div>
              </>
            )}
            {downloadReady && (
              <p className="text-foreground">
                Downloaded — verified SHA-256 matches the manifest. Open the file to install.
              </p>
            )}
            {downloadFailed && (
              <p className="text-destructive">{download?.error ?? 'Download failed'}</p>
            )}
          </div>
        )}

        {/* Manual install instructions — only for platforms without a
            one-click installer. In-place platforms use "Install & restart". */}
        {downloadReady && !inPlaceInstallSupported && (
          <p className="text-xs text-muted-foreground border-l-2 border-primary/30 pl-2">
            {platformInstructions(state.platform)}
          </p>
        )}

        <div className="flex flex-col gap-2 pt-2">
          {downloadActive && (
            <Button variant="outline" onClick={() => cancelDownload()} className="w-full">
              Cancel download
            </Button>
          )}
          {!downloadActive && !downloadReady && state.platform_supported && (
            <Button onClick={() => downloadUpdate()} className="w-full">
              <Download className="w-4 h-4 mr-2" />
              {downloadFailed ? 'Retry download' : 'Download update'}
            </Button>
          )}
          {downloadReady && download?.local_path && (
            <>
              {inPlaceInstallSupported ? (
                <Button onClick={() => installUpdate()} className="w-full">
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Install & restart
                </Button>
              ) : (
                <Button onClick={() => revealDownload(download.local_path!)} className="w-full">
                  <FolderOpen className="w-4 h-4 mr-2" />
                  Open downloaded file
                </Button>
              )}
            </>
          )}
          {!state.platform_supported && state.release_notes_url && (
            <Button onClick={() => openReleaseNotes(state.release_notes_url!)} className="w-full">
              <ExternalLink className="w-4 h-4 mr-2" />
              Open release page
            </Button>
          )}
          <Button onClick={() => Quit()} variant="outline" className="w-full">
            Quit
          </Button>
        </div>
      </div>
    </div>
  );
}
