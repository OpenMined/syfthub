import { useState, useEffect } from 'react';
import { Pencil } from 'lucide-react';
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
import { Input } from '@/components/ui/input';
import { useAppStore } from '@/stores/appStore';
import { extractErrorMessage } from '@/lib/utils';
import { Spinner } from '@/components/ui/spinner';
import { ErrorBanner } from '@/components/ui/error-banner';

// slugify mirrors the Go nodeops.Slugify rules. It only drives the live
// preview below — the backend runs the authoritative slugify on rename.
function slugify(name: string): string {
  let slug = name.toLowerCase();
  slug = slug.replace(/[\s_]/g, '-');
  slug = slug.replace(/[^a-z0-9-]/g, '');
  while (slug.includes('--')) {
    slug = slug.replace(/--/g, '-');
  }
  slug = slug.replace(/^-+|-+$/g, '');
  return slug;
}

export function RenameEndpointDialog() {
  const {
    isRenameDialogOpen,
    setRenameDialogOpen,
    isRenamingEndpoint,
    renameEndpoint,
    selectedEndpointSlug,
  } = useAppStore();

  const [newName, setNewName] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Seed the input with the current folder name when the dialog opens.
  useEffect(() => {
    if (isRenameDialogOpen) {
      setNewName(selectedEndpointSlug || '');
      setError(null);
    }
  }, [isRenameDialogOpen, selectedEndpointSlug]);

  const newSlug = slugify(newName);
  const isUnchanged = newSlug === selectedEndpointSlug;
  const canRename = newSlug !== '' && !isUnchanged && !isRenamingEndpoint;

  const handleRename = async () => {
    if (!canRename) return;
    setError(null);
    try {
      await renameEndpoint(newName);
    } catch (err) {
      setError(extractErrorMessage(err, 'Failed to rename endpoint'));
    }
  };

  return (
    <AlertDialog open={isRenameDialogOpen} onOpenChange={setRenameDialogOpen}>
      <AlertDialogContent className="sm:max-w-[450px]">
        <AlertDialogHeader className="sm:place-items-center! sm:text-center!">
          <AlertDialogTitle>
            <div className="mx-auto mb-2 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
              <Pencil className="h-7 w-7 text-primary" />
            </div>
            Rename Endpoint Folder
          </AlertDialogTitle>
          <AlertDialogDescription className="text-center text-[15px]">
            This renames the endpoint's folder on disk. Because the hub
            identifies endpoints by their folder name, the endpoint's public URL
            will change and existing links to the old URL will stop working.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <p className="text-sm text-foreground text-center">
              New folder name for{' '}
              <code className="px-1.5 py-0.5 rounded bg-secondary font-mono text-xs">{selectedEndpointSlug}</code>:
            </p>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder={selectedEndpointSlug || ''}
              className="font-mono"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && canRename) {
                  handleRename();
                }
              }}
            />
            {/* Resulting folder name preview */}
            <div className="flex items-center justify-center gap-2 text-xs">
              <span className="text-muted-foreground">Folder:</span>
              {newSlug ? (
                <code className="px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground font-mono">
                  {newSlug}
                </code>
              ) : (
                <span className="text-muted-foreground italic">Enter a name</span>
              )}
              {isUnchanged && newSlug !== '' && (
                <span className="text-muted-foreground">Same as current</span>
              )}
            </div>
          </div>

          <ErrorBanner message={error} className="text-center" />
        </div>

        <AlertDialogFooter className="mt-2 sm:justify-center!">
          <AlertDialogCancel disabled={isRenamingEndpoint}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction onClick={handleRename} disabled={!canRename}>
            {isRenamingEndpoint ? (
              <>
                <Spinner className="-ml-1 mr-2 h-4 w-4" />
                Renaming...
              </>
            ) : (
              'Rename Folder'
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
