import { useState, useEffect } from 'react';
import { OctagonAlert } from 'lucide-react';
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

export function DeleteEndpointDialog() {
  const {
    isDeleteDialogOpen,
    setDeleteDialogOpen,
    isDeletingEndpoint,
    deleteEndpoint,
    selectedEndpointSlug,
  } = useAppStore();

  const [confirmText, setConfirmText] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Reset form when dialog opens/closes
  useEffect(() => {
    if (isDeleteDialogOpen) {
      setConfirmText('');
      setError(null);
    }
  }, [isDeleteDialogOpen]);

  const isConfirmed = confirmText === selectedEndpointSlug;

  const handleDelete = async () => {
    if (!isConfirmed) return;

    setError(null);
    try {
      await deleteEndpoint();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete endpoint');
    }
  };

  return (
    <AlertDialog open={isDeleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
      <AlertDialogContent className="sm:max-w-[450px]">
        <AlertDialogHeader className="items-center">
          <AlertDialogTitle>
            <div className="mx-auto mb-2 flex h-14 w-14 items-center justify-center rounded-full bg-destructive/10">
              <OctagonAlert className="h-7 w-7 text-destructive" />
            </div>
            Delete Endpoint
          </AlertDialogTitle>
          <AlertDialogDescription className="text-center text-[15px]">
            This action cannot be undone. This will permanently delete the endpoint
            and all associated files including runner code, environment variables,
            dependencies, policies, and documentation.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-4 py-2">
          {/* Confirmation input */}
          <div className="space-y-2">
            <p className="text-sm text-foreground text-center">
              To confirm, type <code className="px-1.5 py-0.5 rounded bg-secondary text-destructive font-mono text-xs">{selectedEndpointSlug}</code> below:
            </p>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={selectedEndpointSlug || ''}
              className="font-mono"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter' && isConfirmed && !isDeletingEndpoint) {
                  handleDelete();
                }
              }}
            />
          </div>

          {/* Error message */}
          {error && (
            <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm text-center">
              {error}
            </div>
          )}
        </div>

        <AlertDialogFooter className="mt-2 sm:justify-center">
          <AlertDialogCancel disabled={isDeletingEndpoint}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={handleDelete}
            disabled={!isConfirmed || isDeletingEndpoint}
          >
            {isDeletingEndpoint ? (
              <>
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Deleting...
              </>
            ) : (
              'Delete Endpoint'
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
