import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Eye, OctagonAlert, Sparkles, Trash2, Upload } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { Markdown } from '@/components/prompt-kit/markdown';
import { parseFrontmatter } from '@/lib/markdown';
import { formatRelativeTime } from '@/lib/date-utils';
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
  InstallSkillFromPaths,
  ListSkills,
  ReadSkill,
  RemoveSkill,
} from '../../../wailsjs/go/main/App';
import { main } from '../../../wailsjs/go/models';
import { useAppStore } from '../../stores/appStore';
import {
  DropzoneOverlays,
  basename,
  dropzoneBorderClass,
  useWailsDropzone,
} from '../../hooks/use-wails-dropzone';

type SkillInfo = main.SkillInfo;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

// formatRelativeTime imported from @/lib/date-utils — the shared helper uses
// Math.floor and rolls entries older than 24h over to formatShortTime
// (e.g. "Mar 5") instead of the previous Nd / Nmo buckets. The day-rollover
// is an intentional improvement: a day-resolution bucket gets misleading fast
// while an absolute date stays meaningful.

export function SkillsSection({ embedded = false }: { embedded?: boolean } = {}) {
  const selectedEndpointSlug = useAppStore((s) => s.selectedEndpointSlug);
  const selectedEndpointDetail = useAppStore((s) => s.selectedEndpointDetail);
  const isAgent = selectedEndpointDetail?.type === 'agent';
  const outerCls = embedded ? 'space-y-4' : 'p-6 space-y-6';

  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(false);

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

  // The listener is only registered for agent endpoints, so drops on other
  // endpoint types aren't routed here.
  const { dropState, setDropState, runPaths, zoneProps } = useWailsDropzone({
    onPaths: async (paths) => {
      if (!selectedEndpointSlug) return;
      await InstallSkillFromPaths(selectedEndpointSlug, paths);
      await fetchSkills();
    },
    uploadingLabel: (paths) => `Installing ${basename(paths[0]) || 'item'}…`,
    enabled: isAgent,
  });

  const handleBrowse = async () => {
    try {
      const path = await BrowseForFolder('Choose skill folder');
      if (path) {
        await runPaths([path]);
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
      <SkillsHeader
        count={loading ? undefined : skills.length}
        action={
          <Button
            size="sm"
            onClick={handleBrowse}
            className="h-7 text-xs bg-primary text-primary-foreground hover:bg-primary/90"
          >
            New Skill
          </Button>
        }
      />

      <div
        role="region"
        aria-label="Installed skills. Drop a folder or SKILL.md file here to install."
        className={`relative flex flex-col min-h-0 h-[200px] rounded-lg border-2 px-4 py-3 transition-colors duration-150 ease-out ${dropzoneBorderClass(dropState)}`}
        {...zoneProps}
      >
        <p className="text-xs text-muted-foreground mb-3 flex-shrink-0">
          Installed {!loading && skills.length > 0 ? `(${skills.length})` : ''}
        </p>

        {loading ? (
          <div className="flex-1 flex items-center gap-3 justify-center text-muted-foreground">
            <Spinner className="w-5 h-5 text-primary" />
            <span className="text-sm">Loading skills…</span>
          </div>
        ) : skills.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <Upload className="w-10 h-10 mb-3 text-muted-foreground" />
            <p className="text-sm text-foreground">No skills installed yet</p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              Drop a folder or SKILL.md file here to install
            </p>
          </div>
        ) : (
          <ul className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1">
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
                        <Spinner className="w-4 h-4" />
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

        <DropzoneOverlays
          state={dropState}
          dragMessage="Release to install skill"
          onDismissError={() => setDropState({ phase: 'idle' })}
        />
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
              <SkillPreviewBody source={previewBody} />
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
          <AlertDialogHeader className="sm:place-items-center! sm:text-center!">
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
          <AlertDialogFooter className="mt-2 sm:justify-center!">
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

// Render the YAML frontmatter as a metadata header so react-markdown
// doesn't turn the leading `---` into an <hr> and the keys into stray text.
function SkillPreviewBody({ source }: { source: string }) {
  const { frontmatter, body } = parseFrontmatter(source);
  const fmContent = frontmatter
    ? frontmatter.replace(/^---\s*\n?/, '').replace(/\n?---\s*$/, '').trim()
    : '';
  return (
    <div className="px-4 py-3">
      {fmContent && (
        <pre className="mb-4 px-3 py-2 rounded-md border border-border/50 bg-card/40 text-[11px] font-mono text-muted-foreground whitespace-pre-wrap break-words leading-relaxed">
          {fmContent}
        </pre>
      )}
      <Markdown className="markdown-message prose prose-invert max-w-none prose-sm">
        {body}
      </Markdown>
    </div>
  );
}

function SkillsHeader({
  count,
  action,
}: {
  count: number | undefined;
  action?: ReactNode;
}) {
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
      {action}
    </div>
  );
}
