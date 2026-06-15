import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type DragEvent,
} from 'react';
import { OctagonAlert, Upload, X } from 'lucide-react';

import { Spinner } from '@/components/ui/spinner';
import { EventsOn } from '../../wailsjs/runtime/runtime';

export type DropzoneState =
  | { phase: 'idle' }
  | { phase: 'dragover' }
  | { phase: 'uploading'; label: string }
  | { phase: 'error'; message: string };

// basename extracts the final segment of a host path (drop labels).
export function basename(p: string): string {
  return p.split(/[/\\]/).filter(Boolean).pop() ?? '';
}

// dropTargetStyle marks an element as a Wails native file-drop target. The CSS
// property name and value match the DragAndDrop options configured in main.go
// ("--wails-drop-target": "drop"); Wails uses this marker to decide which DOM
// element to deliver OS file drops to. Included in zoneProps.style.
const dropTargetStyle: CSSProperties = {
  ['--wails-drop-target' as unknown as keyof CSSProperties]: 'drop',
} as CSSProperties;

/**
 * useWailsDropzone owns the full contract for a Wails native file-drop zone:
 *
 * - Wails emits a single window-wide `wails:file-drop` event (x, y, paths), so
 *   when several zones are mounted at once (e.g. Skills + Mounts in the
 *   Overview pane) each must gate on its own hover state to avoid consuming a
 *   drop meant for another zone. The hook tracks that with an `isOver` ref.
 * - `dragDepth` tracks nested dragenter/leave so the visual state only resets
 *   when the cursor truly leaves the zone — bubbled events from inner children
 *   otherwise cause flicker.
 * - The listener is registered via EventsOn's per-listener cancel fn, never
 *   EventsOff('wails:file-drop'), which would tear down other zones' listeners.
 * - The HTML drop event is purely cosmetic — Wails delivers the paths via
 *   wails:file-drop; the hook just stages "uploading" for instant feedback.
 * - The hook also owns the uploading → idle/error state sequence around
 *   `onPaths`, so consumers write only the actual work. `runPaths` exposes the
 *   same sequence for non-drop entry points (e.g. a Browse… button).
 *
 * `onPaths` does the work for the dropped host paths; `uploadingLabel` names
 * the overlay label for a drop; set `enabled: false` to keep the zone inert
 * (no listener) while its section is not applicable.
 */
export function useWailsDropzone({
  onPaths,
  uploadingLabel,
  enabled = true,
}: {
  onPaths: (paths: string[]) => void | Promise<void>;
  uploadingLabel: (paths: string[]) => string;
  enabled?: boolean;
}) {
  const [dropState, setDropState] = useState<DropzoneState>({ phase: 'idle' });
  const dragDepth = useRef(0);
  const isOver = useRef(false);
  // Keep the latest callbacks without re-registering the Wails listener.
  const onPathsRef = useRef(onPaths);
  onPathsRef.current = onPaths;
  const uploadingLabelRef = useRef(uploadingLabel);
  uploadingLabelRef.current = uploadingLabel;

  const runPaths = useCallback(async (paths: string[]) => {
    if (paths.length === 0) return;
    setDropState({ phase: 'uploading', label: uploadingLabelRef.current(paths) });
    try {
      await onPathsRef.current(paths);
      setDropState({ phase: 'idle' });
    } catch (err) {
      setDropState({ phase: 'error', message: String(err) });
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const handler = (...args: unknown[]) => {
      if (!isOver.current) return;
      isOver.current = false;
      const paths = args[2];
      if (Array.isArray(paths) && paths.every((p) => typeof p === 'string')) {
        dragDepth.current = 0;
        void runPaths(paths as string[]);
      }
    };
    const cancel = EventsOn('wails:file-drop', handler);
    return () => cancel();
  }, [enabled, runPaths]);

  const onDragEnter = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current += 1;
    isOver.current = true;
    setDropState((s) => (s.phase === 'idle' || s.phase === 'error' ? { phase: 'dragover' } : s));
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
  };

  const onDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) {
      isOver.current = false;
      setDropState((s) => (s.phase === 'dragover' ? { phase: 'idle' } : s));
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = 0;
    setDropState((s) =>
      s.phase === 'dragover' ? { phase: 'uploading', label: 'Reading dropped items…' } : s,
    );
  };

  return {
    dropState,
    setDropState,
    runPaths,
    // Spread onto the dropzone element (style marks it as the drop target).
    zoneProps: { onDragEnter, onDragOver, onDragLeave, onDrop, style: dropTargetStyle },
  };
}

/**
 * DropzoneOverlays renders the three transient dropzone states (dragover /
 * uploading / error) as absolute overlays inside the zone element.
 */
export function DropzoneOverlays({
  state,
  dragMessage,
  onDismissError,
}: {
  state: DropzoneState;
  dragMessage: string;
  onDismissError: () => void;
}) {
  if (state.phase === 'dragover') {
    return (
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center rounded-lg bg-primary/5">
        <Upload className="w-8 h-8 mb-2 text-primary" />
        <p className="text-sm text-primary font-medium">{dragMessage}</p>
      </div>
    );
  }
  if (state.phase === 'uploading') {
    return (
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center rounded-lg bg-card/80 backdrop-blur-sm">
        <Spinner className="w-8 h-8 mb-2 text-primary" />
        <p className="text-sm text-foreground">{state.label}</p>
      </div>
    );
  }
  if (state.phase === 'error') {
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center rounded-lg bg-destructive/5 p-4">
        <OctagonAlert className="w-8 h-8 mb-2 text-destructive" />
        <p className="text-sm text-destructive max-w-sm text-center break-words">{state.message}</p>
        <button
          onClick={onDismissError}
          className="absolute top-2 right-2 p-1 text-muted-foreground hover:text-foreground rounded transition-colors"
          aria-label="Dismiss error"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }
  return null;
}

// dropzoneBorderClass derives the zone's border/background treatment from the
// current state — shared so every dropzone looks and transitions identically.
export function dropzoneBorderClass(state: DropzoneState): string {
  if (state.phase === 'dragover') return 'border-solid border-primary bg-primary/5 ring-2 ring-primary/20';
  if (state.phase === 'error') return 'border-solid border-destructive/40 bg-destructive/5';
  return 'border-dashed border-border/60 bg-card/30';
}
