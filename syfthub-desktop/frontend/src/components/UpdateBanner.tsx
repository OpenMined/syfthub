import { Download, X, ExternalLink, FolderOpen, Loader2, RefreshCw } from 'lucide-react';
import { useUpdate, shouldShowBanner } from '@/contexts/UpdateContext';
import { formatBytes } from '@/lib/utils';

/**
 * UpdateBanner is a thin dismissable strip surfaced at the top of the
 * app shell when a new version is available. In Phase 2 it drives an
 * in-app download flow: progress → reveal-in-file-browser.
 */
export function UpdateBanner() {
  const {
    state, download, dismissedVersion, inPlaceInstallSupported,
    dismissBanner, openReleaseNotes,
    downloadUpdate, cancelDownload, revealDownload, installUpdate,
  } = useUpdate();

  if (!shouldShowBanner(state, dismissedVersion) || !state) return null;

  const handleViewNotes = () => {
    if (state.release_notes_url) {
      openReleaseNotes(state.release_notes_url).catch((err) => {
        console.warn('failed to open release notes:', err);
      });
    }
  };

  // Phase 2 download state mapping. Only show download UI when the
  // download relates to the *current* latest version.
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
      role="status"
      className="px-4 py-2 bg-primary/10 border-b border-primary/20 flex items-center justify-between flex-shrink-0 gap-3"
    >
      <div className="flex items-center gap-2 text-sm min-w-0 flex-1">
        <Download className="w-4 h-4 text-primary flex-shrink-0" />
        <span className="text-foreground truncate">
          {downloadActive && (
            <>
              Downloading v{state.latest_version} —{' '}
              <span className="font-mono text-xs">
                {formatBytes(download.bytes_done)} / {formatBytes(download.bytes_total)}
              </span>
            </>
          )}
          {downloadReady && (
            <>Update downloaded — <span className="font-medium">v{state.latest_version}</span> ready to install</>
          )}
          {downloadFailed && (
            <>Download failed: {download?.error ?? 'unknown error'}</>
          )}
          {!downloadActive && !downloadReady && !downloadFailed && (
            <>
              A new version is available — <span className="font-medium">v{state.latest_version}</span>
              {state.download_size_bytes ? <span className="text-xs text-muted-foreground"> ({formatBytes(state.download_size_bytes)})</span> : null}
            </>
          )}
        </span>
      </div>

      <div className="flex items-center gap-1 flex-shrink-0">
        {downloadActive && (
          <button
            onClick={() => cancelDownload()}
            className="text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded transition-colors"
          >
            Cancel
          </button>
        )}
        {downloadReady && download?.local_path && (
          <>
            {inPlaceInstallSupported ? (
              <button
                onClick={() => installUpdate()}
                className="text-xs font-medium text-primary hover:underline flex items-center gap-1 px-2 py-1 rounded transition-colors"
              >
                <RefreshCw className="w-3 h-3" />
                Install & restart
              </button>
            ) : (
              <button
                onClick={() => revealDownload(download.local_path!)}
                className="text-xs text-primary hover:underline flex items-center gap-1 px-2 py-1 rounded transition-colors"
              >
                <FolderOpen className="w-3 h-3" />
                Open in file browser
              </button>
            )}
          </>
        )}
        {!downloadActive && !downloadReady && state.platform_supported && (
          <button
            onClick={() => downloadUpdate()}
            disabled={downloadActive}
            className="text-xs text-primary hover:underline flex items-center gap-1 px-2 py-1 rounded transition-colors disabled:opacity-50"
          >
            {downloadActive ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
            {downloadFailed ? 'Retry download' : 'Download'}
          </button>
        )}
        <button
          onClick={handleViewNotes}
          className="text-xs text-primary hover:underline flex items-center gap-1 px-2 py-1 rounded transition-colors"
        >
          View release notes
          <ExternalLink className="w-3 h-3" />
        </button>
        <button
          onClick={dismissBanner}
          className="text-muted-foreground hover:text-foreground p-1 rounded transition-colors"
          aria-label="Dismiss update notification"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
