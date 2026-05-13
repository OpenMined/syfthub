import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type CSSProperties,
} from 'react';
import { BookOpen, Eye, OctagonAlert, Sparkles, Trash2, Upload, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import {
  BrowseForFolder,
  BrowseForSkillFile,
  InstallSkillFromPaths,
  ListSkills,
  ReadSkill,
  RemoveSkill,
} from '../../../wailsjs/go/main/App';
import { EventsOn, EventsOff } from '../../../wailsjs/runtime/runtime';
import { main } from '../../../wailsjs/go/models';
import { useAppStore } from '../../stores/appStore';

type SkillInfo = main.SkillInfo;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatRelativeTime(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  const diff = Date.now() - t;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return 'just now';
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 30) return `${day}d ago`;
  const mo = Math.round(day / 30);
  return `${mo}mo ago`;
}

type DropzoneState =
  | { phase: 'idle' }
  | { phase: 'dragover' }
  | { phase: 'uploading'; label: string }
  | { phase: 'error'; message: string };

export function SkillsSection({ embedded = false }: { embedded?: boolean } = {}) {
  const { selectedEndpointSlug, selectedEndpointDetail } = useAppStore();
  const isAgent = selectedEndpointDetail?.type === 'agent';
  const outerCls = embedded ? 'space-y-4' : 'p-6 space-y-6';

  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [dropState, setDropState] = useState<DropzoneState>({ phase: 'idle' });
  // dragDepth tracks nested dragenter/leave so the visual state only resets
  // when the cursor truly leaves the dropzone — bubbled events from inner
  // children otherwise cause flicker.
  const dragDepth = useRef(0);

  // Preview Sheet state
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewSkill, setPreviewSkill] = useState<SkillInfo | null>(null);
  const [previewBody, setPreviewBody] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);

  // Delete confirmation state
  const [toDelete, setToDelete] = useState<SkillInfo | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchSkills = useCallback(async () => {
    if (!selectedEndpointSlug) return;
    setLoading(true);
    try {
      const result = await ListSkills(selectedEndpointSlug);
      setSkills(result || []);
    } catch (err) {
      console.error('Failed to list skills:', err);
      setSkills([]);
    } finally {
      setLoading(false);
    }
  }, [selectedEndpointSlug]);

  useEffect(() => {
    if (isAgent) {
      void fetchSkills();
    }
  }, [fetchSkills, isAgent]);

  const installFromPaths = useCallback(
    async (paths: string[]) => {
      if (!selectedEndpointSlug || paths.length === 0) return;
      const label = paths[0].split(/[/\\]/).pop() ?? 'item';
      setDropState({ phase: 'uploading', label: `Installing ${label}…` });
      try {
        await InstallSkillFromPaths(selectedEndpointSlug, paths);
        setDropState({ phase: 'idle' });
        await fetchSkills();
      } catch (err) {
        setDropState({ phase: 'error', message: String(err) });
      }
    },
    [selectedEndpointSlug, fetchSkills],
  );

  // Listen for Wails native file drop. We only register this while
  // SkillsSection is mounted, so drops on other settings sections aren't
  // routed here.
  useEffect(() => {
    if (!isAgent) return;
    const handler = (...args: unknown[]) => {
      // Wails emits (x, y, paths). We don't care about coordinates because
      // the dropzone is the only drop target on this section.
      const paths = args[2];
      if (Array.isArray(paths) && paths.every((p) => typeof p === 'string')) {
        dragDepth.current = 0;
        void installFromPaths(paths as string[]);
      }
    };
    EventsOn('wails:file-drop', handler);
    return () => EventsOff('wails:file-drop');
  }, [isAgent, installFromPaths]);

  const handleDragEnter = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current += 1;
    if (dropState.phase === 'idle' || dropState.phase === 'error') {
      setDropState({ phase: 'dragover' });
    }
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'copy';
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0 && dropState.phase === 'dragover') {
      setDropState({ phase: 'idle' });
    }
  };

  // The HTML drop event is purely cosmetic now — Wails handles the actual
  // file delivery via wails:file-drop. We just stage the "uploading" state
  // so the user gets immediate feedback; the install completes when the
  // wails:file-drop handler fires.
  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepth.current = 0;
    if (dropState.phase === 'dragover') {
      setDropState({ phase: 'uploading', label: 'Reading dropped items…' });
    }
  };

  const handleBrowseFile = async () => {
    try {
      const path = await BrowseForSkillFile('Choose SKILL.md');
      if (path) {
        await installFromPaths([path]);
      }
    } catch (err) {
      setDropState({ phase: 'error', message: String(err) });
    }
  };

  const handleBrowseFolder = async () => {
    try {
      const path = await BrowseForFolder('Choose skill folder');
      if (path) {
        await installFromPaths([path]);
      }
    } catch (err) {
      setDropState({ phase: 'error', message: String(err) });
    }
  };

  const openPreview = async (skill: SkillInfo) => {
    if (!selectedEndpointSlug) return;
    setPreviewSkill(skill);
    setPreviewOpen(true);
    setPreviewBody('');
    setPreviewLoading(true);
    try {
      const body = await ReadSkill(selectedEndpointSlug, skill.name);
      setPreviewBody(body);
    } catch (err) {
      setPreviewBody(`Failed to load: ${err}`);
    } finally {
      setPreviewLoading(false);
    }
  };

  const confirmDelete = async () => {
    if (!selectedEndpointSlug || !toDelete) return;
    const target = toDelete;
    setDeleting(target.name);
    setToDelete(null);
    try {
      await RemoveSkill(selectedEndpointSlug, target.name);
      await fetchSkills();
    } catch (err) {
      console.error('Failed to delete skill:', err);
    } finally {
      setDeleting(null);
    }
  };

  if (!isAgent) {
    return (
      <div className={outerCls}>
        <SkillsHeader count={undefined} />
        <div className="py-8 text-center">
          <Sparkles className="w-10 h-10 mx-auto mb-3 text-secondary" />
          <p className="text-sm text-muted-foreground">Skills are only available for agent endpoints</p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            Change the endpoint type to <code className="text-secondary-foreground">agent</code> to manage skills.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={outerCls}>
      <SkillsHeader count={loading ? undefined : skills.length} />

      <Dropzone
        state={dropState}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onBrowseFile={handleBrowseFile}
        onBrowseFolder={handleBrowseFolder}
        onDismissError={() => setDropState({ phase: 'idle' })}
      />

      <div>
        <p className="text-xs text-muted-foreground mb-3">
          Installed {!loading && skills.length > 0 ? `(${skills.length})` : ''}
        </p>

        {loading ? (
          <div className="flex items-center gap-3 py-8 justify-center text-muted-foreground">
            <div className="w-5 h-5 border-2 border-secondary border-t-primary rounded-full animate-spin" />
            <span className="text-sm">Loading skills…</span>
          </div>
        ) : skills.length === 0 ? (
          <div className="py-8 text-center">
            <BookOpen className="w-10 h-10 mx-auto mb-3 text-secondary" />
            <p className="text-sm text-muted-foreground">No skills installed yet</p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              Drag a folder or SKILL.md file into the area above
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {skills.map((skill) => (
              <li
                key={skill.name}
                className="group flex items-center gap-3 px-3 py-2 rounded-lg bg-card/50 border border-border/50 transition-colors hover:bg-card/70"
              >
                <Sparkles className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-foreground truncate">{skill.title || skill.name}</p>
                  <p className="font-mono text-xs text-muted-foreground truncate">{skill.name}</p>
                </div>
                <span className="hidden sm:inline text-xs text-muted-foreground tabular-nums min-w-[60px] text-right">
                  {formatBytes(skill.size)}
                </span>
                <span className="hidden md:inline text-xs text-muted-foreground tabular-nums min-w-[68px] text-right">
                  {formatRelativeTime(skill.modifiedAt)}
                </span>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => openPreview(skill)}
                      className="p-1.5 text-muted-foreground hover:text-primary transition-colors rounded hover:bg-secondary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
                      aria-label={`Preview ${skill.name}`}
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top"><p>Preview</p></TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => setToDelete(skill)}
                      disabled={deleting === skill.name}
                      className="p-1.5 text-muted-foreground hover:text-destructive transition-colors rounded hover:bg-secondary/50 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive/50"
                      aria-label={`Delete ${skill.name}`}
                    >
                      {deleting === skill.name ? (
                        <span className="w-4 h-4 border border-muted-foreground border-t-foreground rounded-full animate-spin block" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top"><p>Delete</p></TooltipContent>
                </Tooltip>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Preview Sheet */}
      <Sheet open={previewOpen} onOpenChange={setPreviewOpen}>
        <SheetContent side="right" className="w-[600px] sm:max-w-[600px] p-0 flex flex-col">
          <SheetHeader className="px-4 py-3 border-b border-border/50 flex-shrink-0">
            <SheetTitle className="text-base flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-primary" />
              {previewSkill?.title || previewSkill?.name || 'Skill'}
            </SheetTitle>
            {previewSkill && (
              <p className="font-mono text-xs text-muted-foreground">{previewSkill.name}</p>
            )}
          </SheetHeader>
          <div className="flex-1 overflow-y-auto">
            {previewLoading ? (
              <div className="h-full flex items-center justify-center text-muted-foreground">
                <div className="text-center">
                  <div className="w-6 h-6 border-2 border-secondary border-t-primary rounded-full animate-spin mx-auto mb-2" />
                  <p className="text-xs">Loading…</p>
                </div>
              </div>
            ) : (
              <pre className="px-4 py-3 text-xs font-mono text-foreground whitespace-pre-wrap break-words leading-relaxed">
                {previewBody}
              </pre>
            )}
          </div>
          <div className="flex-shrink-0 px-4 py-1.5 border-t border-border/50 bg-card/30 text-xs text-muted-foreground flex items-center justify-between">
            <span>SKILL.md</span>
            <span className="text-muted-foreground/70 tabular-nums">
              {previewSkill ? formatBytes(previewSkill.size) : ''}
            </span>
          </div>
        </SheetContent>
      </Sheet>

      {/* Delete confirmation */}
      <AlertDialog open={!!toDelete} onOpenChange={(open) => !open && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader className="items-center">
            <AlertDialogTitle>
              <div className="mx-auto mb-2 flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10">
                <OctagonAlert className="h-7 w-7 text-destructive" />
              </div>
              Delete Skill
            </AlertDialogTitle>
            <AlertDialogDescription className="text-center text-[15px]">
              Delete "{toDelete?.name}" and all its files? This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="mt-2 sm:justify-center">
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={confirmDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Sub-components
// ----------------------------------------------------------------------------

function SkillsHeader({ count }: { count: number | undefined }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-medium text-foreground">Skills</h2>
        {count !== undefined && (
          <span className="px-2 py-0.5 rounded text-xs bg-secondary text-secondary-foreground">
            {count}
          </span>
        )}
      </div>
    </div>
  );
}

interface DropzoneProps {
  state: DropzoneState;
  onDragEnter: (e: DragEvent<HTMLDivElement>) => void;
  onDragOver: (e: DragEvent<HTMLDivElement>) => void;
  onDragLeave: (e: DragEvent<HTMLDivElement>) => void;
  onDrop: (e: DragEvent<HTMLDivElement>) => void;
  onBrowseFile: () => void;
  onBrowseFolder: () => void;
  onDismissError: () => void;
}

// dropTargetStyle marks this element as a Wails native file-drop target.
// The CSS property name and value match the DragAndDrop options configured
// in main.go ("--wails-drop-target": "drop"); Wails uses this marker to
// decide which DOM element to deliver OS file drops to.
const dropTargetStyle: CSSProperties = {
  ['--wails-drop-target' as unknown as keyof CSSProperties]: 'drop',
} as CSSProperties;

function Dropzone({
  state,
  onDragEnter,
  onDragOver,
  onDragLeave,
  onDrop,
  onBrowseFile,
  onBrowseFolder,
  onDismissError,
}: DropzoneProps) {
  let containerCls =
    'relative rounded-lg px-6 py-10 transition-colors duration-150 ease-out border-2 ';
  switch (state.phase) {
    case 'dragover':
      containerCls += 'border-solid border-primary bg-primary/5 ring-2 ring-primary/20';
      break;
    case 'uploading':
      containerCls += 'border-dashed border-border/60 bg-card/30';
      break;
    case 'error':
      containerCls += 'border-solid border-destructive/40 bg-destructive/5';
      break;
    case 'idle':
    default:
      containerCls += 'border-dashed border-border/60 bg-card/30 hover:bg-card/40';
      break;
  }

  return (
    <div
      role="region"
      aria-label="Install a skill by dropping a folder or a SKILL.md file"
      className={containerCls}
      style={dropTargetStyle}
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <div className="pointer-events-none flex flex-col items-center text-center">
        {state.phase === 'uploading' ? (
          <div className="w-8 h-8 mb-3 border-2 border-secondary border-t-primary rounded-full animate-spin" />
        ) : state.phase === 'error' ? (
          <OctagonAlert className="w-8 h-8 mb-3 text-destructive" />
        ) : (
          <Upload
            className={`w-8 h-8 mb-3 ${state.phase === 'dragover' ? 'text-primary' : 'text-muted-foreground'}`}
          />
        )}
        <div aria-live="polite">
          {state.phase === 'idle' && (
            <>
              <p className="text-sm text-foreground">Drop a folder or SKILL.md file here</p>
              <p className="text-xs text-muted-foreground mt-1">
                The folder must contain a SKILL.md at its root
              </p>
            </>
          )}
          {state.phase === 'dragover' && (
            <p className="text-sm text-primary font-medium">Release to install skill</p>
          )}
          {state.phase === 'uploading' && (
            <p className="text-sm text-foreground">{state.label}</p>
          )}
          {state.phase === 'error' && (
            <p className="text-sm text-destructive max-w-sm">{state.message}</p>
          )}
        </div>
      </div>

      {(state.phase === 'idle' || state.phase === 'error') && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" onClick={onBrowseFile} className="h-8 text-xs">
            Browse SKILL.md
          </Button>
          <Button variant="outline" size="sm" onClick={onBrowseFolder} className="h-8 text-xs">
            Browse Folder
          </Button>
        </div>
      )}

      {state.phase === 'error' && (
        <button
          onClick={onDismissError}
          className="absolute top-2 right-2 p-1 text-muted-foreground hover:text-foreground rounded transition-colors"
          aria-label="Dismiss error"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
