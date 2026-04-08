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
import { extractErrorMessage } from '@/lib/utils';
import { Spinner } from '@/components/ui/spinner';
import { ErrorBanner } from '@/components/ui/error-banner';

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
      setError(extractErrorMessage(err, 'Failed to delete endpoint'));
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
          <ErrorBanner message={error} className="text-center" />
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
                <Spinner className="-ml-1 mr-2 h-4 w-4" />
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
