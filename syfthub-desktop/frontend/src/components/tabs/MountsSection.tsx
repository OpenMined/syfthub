import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  File,
  Folder,
  HardDriveUpload,
  Trash2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
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

import {
  AddEndpointMounts,
  BrowseForFolder,
  DeleteEndpointMount,
  GetEndpointMounts,
  SetEndpointMount,
} from '../../../wailsjs/go/main/App';
import { main } from '../../../wailsjs/go/models';
import { useAppStore } from '../../stores/appStore';
import {
  DropzoneOverlays,
  basename,
  dropzoneBorderClass,
  useWailsDropzone,
} from '../../hooks/use-wails-dropzone';

type MountEntry = main.MountEntry;

/**
 * MountsSection manages an endpoint's container bind mounts (README.md
 * frontmatter `container.mounts`). It mirrors SkillsSection: a drag-and-drop
 * zone where the user drops host folders/files (or clicks "Add mount" to pick
 * one). The Go binding mounts each item at /home/runner/volumes/<basename>,
 * read-only by default; the per-row RO/RW pill flips it.
 */
export function MountsSection() {
  const selectedEndpointSlug = useAppStore((s) => s.selectedEndpointSlug);
  const containerEnabled = useAppStore((s) => s.config?.containerEnabled ?? false);

  const [mounts, setMounts] = useState<MountEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const [toDelete, setToDelete] = useState<MountEntry | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchMounts = useCallback(async () => {
    if (!selectedEndpointSlug) return;
    setLoading(true);
    try {
      const result = await GetEndpointMounts(selectedEndpointSlug);
      setMounts(result || []);
    } catch (err) {
      console.error('Failed to list mounts:', err);
      setMounts([]);
    } finally {
      setLoading(false);
    }
  }, [selectedEndpointSlug]);

  useEffect(() => {
    void fetchMounts();
  }, [fetchMounts]);

  const { dropState, setDropState, runPaths, zoneProps } = useWailsDropzone({
    onPaths: async (paths) => {
      if (!selectedEndpointSlug) return;
      // One batch call → one frontmatter write + one endpoint reload,
      // however many items were dropped.
      await AddEndpointMounts(selectedEndpointSlug, paths);
      await fetchMounts();
    },
    uploadingLabel: (paths) =>
      paths.length > 1
        ? `Mounting ${paths.length} items…`
        : `Mounting ${basename(paths[0]) || 'item'}…`,
  });

  const handleBrowse = async () => {
    try {
      const path = await BrowseForFolder('Choose a folder to mount');
      if (path) await runPaths([path]);
    } catch (err) {
      setDropState({ phase: 'error', message: String(err) });
    }
  };

  const togglePermission = async (m: MountEntry) => {
    if (!selectedEndpointSlug) return;
    try {
      await SetEndpointMount(selectedEndpointSlug, m.source, m.target, !m.readOnly);
      await fetchMounts();
    } catch (err) {
      console.error('Failed to toggle mount permission:', err);
    }
  };

  const handleDelete = async () => {
    if (!selectedEndpointSlug || !toDelete) return;
    const target = toDelete.target;
    setDeleting(target);
    setToDelete(null);
    try {
      await DeleteEndpointMount(selectedEndpointSlug, target);
      await fetchMounts();
    } catch (err) {
      console.error('Failed to delete mount:', err);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-medium text-foreground">Mounts</h2>
          {mounts.length > 0 && (
            <span className="px-2 py-0.5 rounded text-xs bg-secondary text-secondary-foreground tabular-nums">
              {mounts.length}
            </span>
          )}
        </div>
        <Button
          size="sm"
          onClick={handleBrowse}
          disabled={!selectedEndpointSlug}
          className="h-7 text-xs bg-primary text-primary-foreground hover:bg-primary/90"
        >
          Add mount
        </Button>
      </div>

      {!containerEnabled && (
        <div className="flex items-start gap-1.5 text-xs text-chart-3">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          <span>
            Mounts apply in <span className="font-medium">container mode</span> only. Enable it in
            Settings for these to take effect.
          </span>
        </div>
      )}

      <div
        role="region"
        aria-label="Mounted folders. Drop a folder or file here to mount it into the agent."
        className={`relative flex flex-col min-h-0 h-[200px] rounded-lg border-2 px-4 py-3 transition-colors duration-150 ease-out ${dropzoneBorderClass(dropState)}`}
        {...zoneProps}
      >
        <p className="text-xs text-muted-foreground mb-3 flex-shrink-0">
          Mounted {!loading && mounts.length > 0 ? `(${mounts.length})` : ''}
        </p>

        {loading ? (
          <div className="flex-1 flex items-center gap-3 justify-center text-muted-foreground">
            <Spinner className="w-5 h-5 text-primary" />
            <span className="text-sm">Loading mounts…</span>
          </div>
        ) : mounts.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
            <HardDriveUpload className="w-10 h-10 mb-3 text-muted-foreground" />
            <p className="text-sm text-foreground">No folders mounted yet</p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              Drop a folder or file here to mount it. Only what you mount is visible to the agent —
              the rest of your machine stays invisible.
            </p>
          </div>
        ) : (
          <ul className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1">
            {mounts.map((m) => (
              <li
                key={m.target}
                className="group flex items-center gap-3 px-3 py-2 rounded-lg bg-card/50 border border-border/50 transition-colors hover:bg-card/70"
              >
                {m.isDir ? (
                  <Folder className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                ) : (
                  <File className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-foreground truncate" title={m.source}>
                    {m.source}
                  </p>
                  <p className="font-mono text-xs text-muted-foreground truncate" title={m.target}>
                    {m.target}
                  </p>
                </div>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => togglePermission(m)}
                      aria-label={
                        m.readOnly
                          ? 'Read-only — click to allow writes'
                          : 'Writable — click to make read-only'
                      }
                      className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                        m.readOnly
                          ? 'text-muted-foreground hover:bg-secondary/60'
                          : 'bg-chart-3/20 text-chart-3 hover:bg-chart-3/30'
                      }`}
                    >
                      {m.readOnly ? 'RO' : 'RW'}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top">
                    <p>
                      {m.readOnly
                        ? 'Read-only — click to allow writes'
                        : 'Writable — agent can modify these files'}
                    </p>
                  </TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => setToDelete(m)}
                      disabled={deleting === m.target}
                      aria-label={`Remove mount ${m.target}`}
                      className="p-1.5 text-muted-foreground hover:text-destructive transition-colors rounded hover:bg-secondary/50 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive/50"
                    >
                      {deleting === m.target ? (
                        <Spinner className="w-4 h-4" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top"><p>Remove</p></TooltipContent>
                </Tooltip>
              </li>
            ))}
          </ul>
        )}

        <DropzoneOverlays
          state={dropState}
          dragMessage="Release to mount"
          onDismissError={() => setDropState({ phase: 'idle' })}
        />
      </div>

      <AlertDialog open={toDelete !== null} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this mount?</AlertDialogTitle>
            <AlertDialogDescription>
              The agent will no longer see{' '}
              <span className="font-mono text-foreground">{toDelete?.target}</span>.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-white hover:bg-destructive/90"
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
