import { useState } from 'react';
import { ChevronDown, Eye, EyeOff, Folder } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { DEFAULT_SYFTHUB_URL, isValidUrl } from '@/lib/utils';

interface AdvancedSettingsProps {
  syfthubUrl: string;
  onSyfthubUrlChange: (url: string) => void;
  endpointsPath: string;
  /** Raw user-entered path (may be empty -> default is used). */
  onEndpointsPathChange: (path: string) => void;
  defaultEndpointsPath: string;
  onBrowse: () => void;
  hostname: string;
  /** Disable inputs (e.g. while a request is in flight). */
  disabled?: boolean;
  /** Called when the user submits a pasted API key via the escape hatch. */
  onUseApiKey: (apiKey: string) => void;
  /** Whether the API-key submission is currently in flight. */
  apiKeyBusy?: boolean;
}

/** The collapsible "Advanced settings" section: SyftHub server URL, endpoints
 *  folder picker, and the "paste an API key instead" escape hatch. */
export function AdvancedSettings({
  syfthubUrl,
  onSyfthubUrlChange,
  endpointsPath,
  onEndpointsPathChange,
  defaultEndpointsPath,
  onBrowse,
  hostname,
  disabled,
  onUseApiKey,
  apiKeyBusy,
}: AdvancedSettingsProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [apiKeyOpen, setApiKeyOpen] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);

  const isUrlValid = isValidUrl(syfthubUrl);
  const hasApiKey = apiKey.trim().length > 0;

  return (
    <div className="pt-1 border-t border-border/40">
      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="w-full flex items-center justify-between py-2.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <span className="flex items-center gap-1.5">
              <ChevronDown
                className={`w-3.5 h-3.5 transition-transform ${
                  advancedOpen ? '' : '-rotate-90'
                }`}
              />
              Advanced settings
            </span>
            {!advancedOpen && (
              <span className="font-mono text-[11px] truncate max-w-[180px] text-right text-muted-foreground/70">
                {hostname}
              </span>
            )}
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-4 pt-2 pb-1">
          <div className="space-y-1.5">
            <Label
              htmlFor="syfthubUrl"
              className="text-xs text-muted-foreground font-normal"
            >
              SyftHub server
            </Label>
            <Input
              id="syfthubUrl"
              type="url"
              value={syfthubUrl}
              disabled={disabled}
              onChange={(e) => onSyfthubUrlChange(e.target.value)}
              placeholder={DEFAULT_SYFTHUB_URL}
              className={`h-9 text-sm ${
                syfthubUrl && !isUrlValid
                  ? 'border-destructive focus-visible:border-destructive'
                  : ''
              }`}
            />
            {syfthubUrl && !isUrlValid && (
              <p className="text-[11px] text-destructive">
                Please enter a valid URL
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label
              htmlFor="endpointsPath"
              className="text-xs text-muted-foreground font-normal"
            >
              Endpoints folder
            </Label>
            <div className="flex gap-2">
              <Input
                id="endpointsPath"
                type="text"
                value={endpointsPath}
                disabled={disabled}
                onChange={(e) => onEndpointsPathChange(e.target.value)}
                placeholder={defaultEndpointsPath || '.endpoints'}
                className="h-9 flex-1 text-sm font-mono"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onBrowse}
                disabled={disabled}
                aria-label="Browse for endpoints folder"
                className="h-9 px-3"
              >
                <Folder className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>

          <div className="pt-1 border-t border-border/40">
            <Collapsible open={apiKeyOpen} onOpenChange={setApiKeyOpen}>
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className="w-full flex items-center gap-1.5 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  <ChevronDown
                    className={`w-3.5 h-3.5 transition-transform ${
                      apiKeyOpen ? '' : '-rotate-90'
                    }`}
                  />
                  Paste an API key instead
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-3 pt-1 pb-1">
                <p className="text-[11px] text-muted-foreground">
                  Already have a personal access token? Use it directly instead
                  of signing in.
                </p>
                <div className="space-y-2">
                  <Label htmlFor="apiKey" className="sr-only">
                    API key
                  </Label>
                  <div className="relative">
                    <Input
                      id="apiKey"
                      type={showApiKey ? 'text' : 'password'}
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder="syft_pat_..."
                      autoComplete="off"
                      spellCheck={false}
                      disabled={disabled || apiKeyBusy}
                      className="h-10 pr-11 font-mono text-sm tracking-tight"
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey((v) => !v)}
                      aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:text-foreground"
                    >
                      {showApiKey ? (
                        <EyeOff className="w-4 h-4" />
                      ) : (
                        <Eye className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => onUseApiKey(apiKey.trim())}
                    disabled={
                      disabled || apiKeyBusy || !hasApiKey || !isUrlValid
                    }
                    className="w-full h-9"
                  >
                    {apiKeyBusy ? 'Saving…' : 'Use this key'}
                  </Button>
                  <p className="text-[11px] text-muted-foreground">
                    Don't have one?{' '}
                    <a
                      href={`${syfthubUrl}/profile`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary underline-offset-2 hover:underline"
                    >
                      Generate one on {hostname}
                    </a>
                  </p>
                </div>
              </CollapsibleContent>
            </Collapsible>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
