import { RefreshCw, AlertCircle } from 'lucide-react';
import { useUpdate } from '@/contexts/UpdateContext';

/**
 * InstallProgress is the non-dismissable full-screen overlay shown
 * while the binary is being swapped and the app is about to relaunch.
 *
 * Visible whenever updater.InstallState.stage is one of:
 *   preparing | swapping | restarting
 *
 * On failure, the overlay shows the error with a "Dismiss" button —
 * since the install failed, the app remains usable; the user can retry.
 */
export function InstallProgress() {
  const { install } = useUpdate();

  if (!install) return null;
  const active = install.stage === 'preparing' || install.stage === 'swapping' || install.stage === 'restarting';
  const failed = install.stage === 'failed';

  if (!active && !failed) return null;

  return (
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center bg-background/95 backdrop-blur-sm"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="install-title"
    >
      <div className="max-w-md w-full mx-4 bg-card border border-border/60 rounded-lg shadow-2xl p-6 space-y-4">
        {active && (
          <>
            <div className="flex items-center gap-3">
              <RefreshCw className="w-6 h-6 text-primary animate-spin" />
              <div>
                <h2 id="install-title" className="text-lg font-semibold text-foreground">
                  Installing update…
                </h2>
                <p className="text-xs text-muted-foreground">
                  Do not close the window — the app will relaunch automatically.
                </p>
              </div>
            </div>
            {install.step && (
              <p className="text-sm text-muted-foreground border-l-2 border-primary/30 pl-2">
                {install.step}
              </p>
            )}
          </>
        )}
        {failed && (
          <>
            <div className="flex items-center gap-3">
              <AlertCircle className="w-6 h-6 text-destructive" />
              <div>
                <h2 id="install-title" className="text-lg font-semibold text-foreground">
                  Update install failed
                </h2>
                {install.step && (
                  <p className="text-xs text-muted-foreground">at: {install.step}</p>
                )}
              </div>
            </div>
            {install.error && (
              <p className="text-sm text-destructive border-l-2 border-destructive/30 pl-2">
                {install.error}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              The app was not modified. You can retry the install or quit and reinstall manually
              from the release page.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
