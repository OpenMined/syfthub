import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { useSettings } from '@/contexts/SettingsContext';
import { BrowseForFolder } from '../../wailsjs/go/main/App';

interface SettingsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsModal({ open, onOpenChange }: SettingsModalProps) {
  const { settings, saveSettings, defaultEndpointsPath, refreshSettings } = useSettings();

  const [syfthubUrl, setSyfthubUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [endpointsPath, setEndpointsPath] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initialize form with current settings when modal opens
  useEffect(() => {
    if (open && settings) {
      setSyfthubUrl(settings.syfthubUrl || '');
      setApiKey(settings.apiKey || '');
      setEndpointsPath(settings.endpointsPath || defaultEndpointsPath || '');
    }
  }, [open, settings, defaultEndpointsPath]);

  const handleBrowse = async () => {
    const path = await BrowseForFolder('Select Endpoints Directory');
    if (path) {
      setEndpointsPath(path);
    }
  };

  const validateUrl = (url: string): boolean => {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  };

  const handleSave = async () => {
    if (!validateUrl(syfthubUrl)) {
      setError('Please enter a valid URL');
      return;
    }
    if (!endpointsPath) {
      setError('Please specify an endpoints directory');
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await saveSettings(syfthubUrl, apiKey, endpointsPath);
      await refreshSettings();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setError(null);
    onOpenChange(false);
  };

  const isUrlValid = !syfthubUrl || validateUrl(syfthubUrl);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Configure your SyftHub Desktop connection and storage
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* SyftHub URL */}
          <div className="space-y-2">
            <Label htmlFor="settings-syfthubUrl" className="text-foreground">
              SyftHub URL
            </Label>
            <Input
              id="settings-syfthubUrl"
              type="url"
              value={syfthubUrl}
              onChange={(e) => setSyfthubUrl(e.target.value)}
              placeholder="https://syfthub-dev.openmined.org"
              className={!isUrlValid ? 'border-destructive focus:border-destructive' : ''}
            />
            {!isUrlValid && (
              <p className="text-xs text-destructive">Please enter a valid URL</p>
            )}
          </div>

          {/* API Key */}
          <div className="space-y-2">
            <Label htmlFor="settings-apiKey" className="text-foreground">
              API Key <span className="text-muted-foreground text-xs">(optional)</span>
            </Label>
            <Input
              id="settings-apiKey"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Enter your API key"
            />
          </div>

          {/* Endpoints Path */}
          <div className="space-y-2">
            <Label htmlFor="settings-endpointsPath" className="text-foreground">
              Endpoints Directory
            </Label>
            <div className="flex gap-2">
              <Input
                id="settings-endpointsPath"
                type="text"
                value={endpointsPath}
                onChange={(e) => setEndpointsPath(e.target.value)}
                placeholder={defaultEndpointsPath || '.endpoints'}
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                onClick={handleBrowse}
              >
                Browse
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Changing this will require reloading endpoints
            </p>
          </div>

          {error && (
            <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleCancel}
            disabled={isSaving}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={isSaving}
          >
            {isSaving ? 'Saving...' : 'Save Changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
