import { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAppStore } from '@/stores/appStore';
import { extractErrorMessage } from '@/lib/utils';
import { Spinner } from '@/components/ui/spinner';
import { ErrorBanner } from '@/components/ui/error-banner';

// Type options
type EndpointType = 'model' | 'data_source' | 'agent';

// Slugify function (mirrors Go implementation)
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

// Type card component
function TypeCard({
  icon,
  title,
  description,
  selected,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        flex-1 p-4 rounded-lg border-2 text-left transition-all
        ${selected
          ? 'border-primary bg-primary/10'
          : 'border-border hover:border-border/80 bg-card/30 hover:bg-card/50'
        }
      `}
    >
      <div className="flex items-center gap-3 mb-2">
        <span className="text-2xl">{icon}</span>
        <span className={`font-medium ${selected ? 'text-primary' : 'text-foreground'}`}>
          {title}
        </span>
        {selected && (
          <svg className="w-5 h-5 text-primary ml-auto" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{description}</p>
    </button>
  );
}


export function CreateEndpointDialog() {
  const {
    isCreateDialogOpen,
    setCreateDialogOpen,
    isCreatingEndpoint,
    createEndpoint,
    checkEndpointExists,
  } = useAppStore();

  // Form state
  const [name, setName] = useState('');
  // TODO(AGENT_ONLY): Type hardcoded to 'agent'. To restore selection, change back to useState<EndpointType>('model')
  const [type, setType] = useState<EndpointType>('agent');
  const [description, setDescription] = useState('');
  const [version, setVersion] = useState('1.0.0');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Validation state
  const [slug, setSlug] = useState('');
  const [slugExists, setSlugExists] = useState(false);
  const [isCheckingSlug, setIsCheckingSlug] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form when dialog opens/closes
  useEffect(() => {
    if (isCreateDialogOpen) {
      setName('');
      // TODO(AGENT_ONLY): Reset default to 'agent'. To restore, change back to setType('model')
      setType('agent');
      setDescription('');
      setVersion('1.0.0');
      setShowAdvanced(false);
      setSlug('');
      setSlugExists(false);
      setError(null);
    }
  }, [isCreateDialogOpen]);

  // Debounced slug check
  const checkSlug = useCallback(async (name: string) => {
    const generatedSlug = slugify(name);
    setSlug(generatedSlug);

    if (!generatedSlug) {
      setSlugExists(false);
      return;
    }

    setIsCheckingSlug(true);
    try {
      const result = await checkEndpointExists(name);
      setSlugExists(result.exists);
    } finally {
      setIsCheckingSlug(false);
    }
  }, [checkEndpointExists]);

  // Check slug when name changes (with debounce)
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      checkSlug(name);
    }, 300);

    return () => clearTimeout(timeoutId);
  }, [name, checkSlug]);

  // Handle form submission
  const handleCreate = async () => {
    if (!name.trim() || !slug || slugExists) return;

    setError(null);
    try {
      await createEndpoint({
        name: name.trim(),
        type,
        description: description.trim(),
        version: version.trim() || '1.0.0',
      });
    } catch (err) {
      setError(extractErrorMessage(err, 'Failed to create endpoint'));
    }
  };

  // Check if form is valid
  const isValid = name.trim() && slug && !slugExists && !isCheckingSlug;

  return (
    <Dialog open={isCreateDialogOpen} onOpenChange={setCreateDialogOpen}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Create Endpoint</DialogTitle>
          {/* TODO(AGENT_ONLY): Description updated for agent-only. To restore, change back to "model or data source". */}
          <DialogDescription>
            Create a new agent endpoint with bidirectional communication.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-4">
          {/* Name input */}
          <div className="space-y-2">
            <Label htmlFor="endpoint-name">Name</Label>
            <Input
              id="endpoint-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My ML Model"
              autoFocus
            />
            {/* Slug preview */}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Slug:</span>
              {slug ? (
                <>
                  <code className={`px-1.5 py-0.5 rounded ${slugExists ? 'bg-destructive/20 text-destructive' : 'bg-secondary text-secondary-foreground'}`}>
                    {slug}
                  </code>
                  {isCheckingSlug && (
                    <span className="text-muted-foreground">Checking...</span>
                  )}
                  {slugExists && !isCheckingSlug && (
                    <span className="text-destructive">Already exists</span>
                  )}
                </>
              ) : (
                <span className="text-muted-foreground italic">Enter a name to generate slug</span>
              )}
            </div>
          </div>

          {/* TODO(AGENT_ONLY): Type selection hidden — hardcoded to 'agent'.
              To restore, uncomment the entire type selection block below. */}
          {/* <div className="space-y-2">
            <Label>Type</Label>
            <div className="flex gap-3">
              <TypeCard
                icon={<svg className="w-6 h-6 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
                </svg>}
                title="Model"
                description="ML models, LLMs, and inference endpoints"
                selected={type === 'model'}
                onClick={() => setType('model')}
              />
              <TypeCard
                icon={<svg className="w-6 h-6 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
                </svg>}
                title="Data Source"
                description="Databases, APIs, and data connectors"
                selected={type === 'data_source'}
                onClick={() => setType('data_source')}
              />
              <TypeCard
                icon={<svg className="w-6 h-6 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.59 14.37a6 6 0 01-5.84 7.38v-4.8m5.84-2.58a14.98 14.98 0 006.16-12.12A14.98 14.98 0 009.631 8.41m5.96 5.96a14.926 14.926 0 01-5.841 2.58m-.119-8.54a6 6 0 00-7.381 5.84h4.8m2.581-5.84a14.927 14.927 0 00-2.58 5.84m2.699 2.7c-.103.021-.207.041-.311.06a15.09 15.09 0 01-2.448-2.448 14.9 14.9 0 01.06-.312m-2.24 2.39a4.493 4.493 0 00-1.757 4.306 4.493 4.493 0 004.306-1.758M16.5 9a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z" />
                </svg>}
                title="Agent"
                description="Interactive agents with bidirectional communication"
                selected={type === 'agent'}
                onClick={() => setType('agent')}
              />
            </div>
          </div> */}

          {/* Advanced options toggle */}
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <svg
              className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-90' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            Advanced options
          </button>

          {/* Advanced options content */}
          {showAdvanced && (
            <div className="space-y-4 pl-6 border-l-2 border-border">
              {/* Description */}
              <div className="space-y-2">
                <Label htmlFor="endpoint-description">
                  Description <span className="text-muted-foreground text-xs">(optional)</span>
                </Label>
                <textarea
                  id="endpoint-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe what this endpoint does..."
                  rows={2}
                  className="w-full px-3 py-2 text-sm bg-background border border-input rounded-md text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/30 focus:border-ring resize-none"
                />
              </div>

              {/* Version */}
              <div className="space-y-2">
                <Label htmlFor="endpoint-version">Version</Label>
                <Input
                  id="endpoint-version"
                  value={version}
                  onChange={(e) => setVersion(e.target.value)}
                  placeholder="1.0.0"
                  className="w-32"
                />
              </div>
            </div>
          )}

          {/* Error message */}
          <ErrorBanner message={error} />
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => setCreateDialogOpen(false)}
            disabled={isCreatingEndpoint}
          >
            Cancel
          </Button>
          <Button
            onClick={handleCreate}
            disabled={!isValid || isCreatingEndpoint}
          >
            {isCreatingEndpoint ? (
              <>
                <Spinner className="-ml-1 mr-2 h-4 w-4" />
                Creating...
              </>
            ) : (
              'Create Endpoint'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
