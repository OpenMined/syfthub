import { useState, useEffect, useMemo } from 'react';
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
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
// TODO(AGENT_ONLY): Badge import hidden — type badge commented out.
// To restore, uncomment: import { Badge } from '@/components/ui/badge';
import { useAppStore, MULTILINE_ENV_KEYS, type LibraryPackage } from '@/stores/appStore';
// TODO(AGENT_ONLY): typeLabels import hidden. To restore, add typeLabels back:
// import { typeLabels, extractErrorMessage } from '@/lib/utils';
import { extractErrorMessage } from '@/lib/utils';
import { Spinner } from '@/components/ui/spinner';
import { ErrorBanner } from '@/components/ui/error-banner';

function PackageCard({
  pkg,
  isInstalled,
  isInstalling,
  onInstall,
  onUninstall,
}: {
  pkg: LibraryPackage;
  isInstalled: boolean;
  isInstalling: boolean;
  onInstall: () => void;
  onUninstall: () => void;
}) {
  return (
    <div className="flex flex-col rounded-lg border border-border bg-card/50 p-4">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="font-medium text-sm text-foreground leading-tight">{pkg.name}</h3>
        {/* TODO(AGENT_ONLY): Type badge hidden — only agent packages shown.
            To restore, uncomment the Badge below. */}
        {/* <Badge variant="secondary" className="text-[10px] shrink-0">
          {typeLabels[pkg.type] ?? 'Model'}
        </Badge> */}
      </div>

      <p className="text-xs text-muted-foreground mb-3 line-clamp-2 flex-1">
        {pkg.description}
      </p>

      {pkg.tags && pkg.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {pkg.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="text-[10px] px-1.5 py-0.5 rounded bg-secondary/50 text-muted-foreground"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between mt-auto pt-2 border-t border-border/50">
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          {pkg.author && <span>by {pkg.author}</span>}
          {pkg.version && <span>v{pkg.version}</span>}
        </div>

        {isInstalled ? (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-emerald-500 font-medium">Installed</span>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-[10px] text-destructive hover:text-destructive"
              onClick={onUninstall}
              disabled={isInstalling}
            >
              {isInstalling ? 'Removing...' : 'Uninstall'}
            </Button>
          </div>
        ) : (
          <Button
            size="sm"
            className="h-6 px-3 text-[10px]"
            onClick={onInstall}
            disabled={isInstalling}
          >
            Install
          </Button>
        )}
      </div>
    </div>
  );
}

export function LibraryView() {
  const {
    endpoints,
    libraryPackages,
    libraryLoading,
    libraryError,
    installingPackageSlug,
    fetchLibraryPackages,
    installLibraryPackage,
    uninstallLibraryPackage,
  } = useAppStore();

  const [selectedPackage, setSelectedPackage] = useState<LibraryPackage | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);
  const [configValues, setConfigValues] = useState<Record<string, string>>({});
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchLibraryPackages();
  }, [fetchLibraryPackages]);

  const installedSlugs = useMemo(() => new Set(endpoints.map((ep) => ep.slug)), [endpoints]);

  const filteredPackages = useMemo(() => {
    if (!searchQuery) return libraryPackages;
    const query = searchQuery.toLowerCase();
    return libraryPackages.filter(
      (pkg) =>
        pkg.name.toLowerCase().includes(query) ||
        pkg.description.toLowerCase().includes(query) ||
        pkg.tags?.some((t) => t.toLowerCase().includes(query))
    );
  }, [libraryPackages, searchQuery]);

  const handleOpenInstall = (pkg: LibraryPackage) => {
    setSelectedPackage(pkg);
    setInstallError(null);
    // Pre-fill defaults
    const defaults: Record<string, string> = {};
    for (const field of pkg.config ?? []) {
      if (field.default) defaults[field.key] = field.default;
    }
    setConfigValues(defaults);
  };

  const handleInstall = async () => {
    if (!selectedPackage) return;

    setInstallError(null);
    try {
      await installLibraryPackage(selectedPackage.slug, selectedPackage.downloadUrl, configValues);
      setSelectedPackage(null);
    } catch (err) {
      setInstallError(extractErrorMessage(err, String(err)));
    }
  };

  return (
    <div className="h-full flex flex-col p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Library</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Browse and install pre-built endpoint packages
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => fetchLibraryPackages()}
          disabled={libraryLoading}
        >
          {libraryLoading ? 'Loading...' : 'Refresh'}
        </Button>
      </div>

      {/* Search */}
      <div className="mb-4">
        <Input
          placeholder="Search packages..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="h-8 text-xs max-w-sm"
        />
      </div>

      {/* Content */}
      {libraryLoading && libraryPackages.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <Spinner className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">Loading packages...</p>
          </div>
        </div>
      ) : libraryError && libraryPackages.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-sm text-destructive mb-3">{libraryError}</p>
            <Button variant="outline" size="sm" onClick={() => fetchLibraryPackages()}>
              Retry
            </Button>
          </div>
        </div>
      ) : filteredPackages.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-muted-foreground">
            {searchQuery ? 'No packages match your search' : 'No packages available'}
          </p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {filteredPackages.map((pkg) => (
              <PackageCard
                key={pkg.slug}
                pkg={pkg}
                isInstalled={installedSlugs.has(pkg.slug)}
                isInstalling={installingPackageSlug === pkg.slug}
                onInstall={() => handleOpenInstall(pkg)}
                onUninstall={() => uninstallLibraryPackage(pkg.slug)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Install Dialog */}
      <Dialog open={!!selectedPackage} onOpenChange={(open) => { if (!open) { setSelectedPackage(null); setConfigValues({}); } }}>
        <DialogContent className="sm:max-w-[400px]">
          {selectedPackage && (
            <>
              <DialogHeader>
                <DialogTitle className="text-base">Install {selectedPackage.name}</DialogTitle>
                <DialogDescription className="text-xs">
                  This will download and install the package. Setup will run automatically after installation.
                </DialogDescription>
              </DialogHeader>

              {selectedPackage.config && selectedPackage.config.length > 0 && (
                <div className="flex flex-col gap-3 py-1">
                  {selectedPackage.config.map((field) => (
                    <div key={field.key} className="flex flex-col gap-1">
                      <Label htmlFor={`cfg-${field.key}`} className="text-xs font-medium">
                        {field.label}
                        {field.required && <span className="text-destructive ml-0.5">*</span>}
                      </Label>
                      {MULTILINE_ENV_KEYS.has(field.key) ? (
                        <Textarea
                          id={`cfg-${field.key}`}
                          placeholder={field.description || field.default || ''}
                          value={configValues[field.key] ?? ''}
                          onChange={(e) =>
                            setConfigValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                          }
                          className="text-xs min-h-[80px] resize-y"
                        />
                      ) : (
                        <Input
                          id={`cfg-${field.key}`}
                          type={field.secret ? 'password' : 'text'}
                          placeholder={field.description || field.default || ''}
                          value={configValues[field.key] ?? ''}
                          onChange={(e) =>
                            setConfigValues((prev) => ({ ...prev, [field.key]: e.target.value }))
                          }
                          className="h-7 text-xs"
                        />
                      )}
                      {field.description && !MULTILINE_ENV_KEYS.has(field.key) && (
                        <p className="text-[10px] text-muted-foreground">{field.description}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              <ErrorBanner message={installError} className="p-2.5 rounded-md text-xs" />

              <DialogFooter>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedPackage(null)}
                  disabled={installingPackageSlug === selectedPackage.slug}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleInstall}
                  disabled={installingPackageSlug === selectedPackage.slug}
                >
                  {installingPackageSlug === selectedPackage.slug ? (
                    <>
                      <Spinner className="-ml-1 mr-2 h-3 w-3" />
                      Installing...
                    </>
                  ) : (
                    'Install'
                  )}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
