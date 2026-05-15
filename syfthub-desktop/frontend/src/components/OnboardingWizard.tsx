import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, ChevronDown, Eye, EyeOff, Folder } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { OpenMinedIcon } from '@/components/ui/openmined-icon';
import { useSettings } from '@/contexts/SettingsContext';
import { extractErrorMessage, isValidUrl } from '@/lib/utils';
import { BrowseForFolder } from '../../wailsjs/go/main/App';
import { WindowControls } from '@/components/ui/window-controls';
import { ErrorBanner } from '@/components/ui/error-banner';

const isMac = navigator.userAgent.includes('Macintosh');

type WizardStep = 'connect' | 'complete';

const DEFAULT_SYFTHUB_URL = 'https://syfthub-dev.openmined.org';

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export function OnboardingWizard() {
  const { saveSettings, defaultEndpointsPath } = useSettings();
  const [step, setStep] = useState<WizardStep>('connect');
  const [syfthubUrl, setSyfthubUrl] = useState(DEFAULT_SYFTHUB_URL);
  const [apiKey, setApiKey] = useState('');
  const [endpointsPath, setEndpointsPath] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const effectivePath = endpointsPath || defaultEndpointsPath || '.endpoints';
  const isUrlValid = isValidUrl(syfthubUrl);
  const hasApiKey = apiKey.trim().length > 0;
  const canSubmit = isUrlValid && !!effectivePath && hasApiKey && !isSaving;
  const canSkip = isUrlValid && !!effectivePath && !isSaving;
  const hostname = safeHostname(syfthubUrl);

  const handleBrowse = async () => {
    const path = await BrowseForFolder('Select Endpoints Directory');
    if (path) {
      setEndpointsPath(path);
    }
  };

  const handleSave = async (opts: { skipApiKey?: boolean } = {}) => {
    setIsSaving(true);
    setError(null);
    try {
      await saveSettings(syfthubUrl, opts.skipApiKey ? '' : apiKey, effectivePath);
      setStep('complete');
    } catch (err) {
      setError(extractErrorMessage(err, 'Failed to save settings'));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={`h-screen flex flex-col bg-gradient-to-br from-background via-card to-background text-foreground ${!isMac ? 'rounded-xl overflow-hidden shadow-2xl' : ''}`}>
      {isMac ? (
        <div className="wails-drag h-9 flex-shrink-0 border-b border-border/30 bg-background flex items-center justify-center px-3 pl-[80px]">
          <span className="text-xs text-muted-foreground">SyftHub Desktop</span>
        </div>
      ) : (
        <div className="wails-drag h-9 flex-shrink-0 border-b border-border/30 bg-card/30 flex items-center px-3">
          <WindowControls />
          <div className="flex-1 flex items-center justify-center">
            <span className="text-xs text-muted-foreground">SyftHub Desktop</span>
          </div>
          <div className="w-32" />
        </div>
      )}

      <div className="flex-1 overflow-y-auto flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              {step === 'connect' && (
                <Card className="bg-card/50 border-border">
                  <CardContent className="p-8 space-y-7">
                    <div className="flex flex-col items-center text-center space-y-3">
                      <OpenMinedIcon className="w-12 h-12" />
                      <div className="space-y-1.5">
                        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                          Connect to SyftHub
                        </h1>
                        <p className="text-sm text-muted-foreground">
                          Paste your API key to sync endpoints.
                        </p>
                      </div>
                    </div>

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
                          autoFocus
                          autoComplete="off"
                          spellCheck={false}
                          className="h-12 pr-11 font-mono text-sm tracking-tight"
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
                      <p className="text-xs text-muted-foreground">
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

                    <ErrorBanner message={error} />

                    <div className="space-y-3">
                      <Button
                        onClick={() => handleSave()}
                        className="w-full h-11"
                        disabled={!canSubmit}
                      >
                        {isSaving ? 'Connecting…' : 'Connect & Continue'}
                      </Button>
                      <button
                        type="button"
                        onClick={() => handleSave({ skipApiKey: true })}
                        disabled={!canSkip}
                        className="block w-full text-center text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Skip for now · I'll add it later
                      </button>
                    </div>

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
                              onChange={(e) => setSyfthubUrl(e.target.value)}
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
                                value={effectivePath}
                                onChange={(e) => setEndpointsPath(e.target.value)}
                                placeholder={defaultEndpointsPath || '.endpoints'}
                                className="h-9 flex-1 text-sm font-mono"
                              />
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={handleBrowse}
                                aria-label="Browse for endpoints folder"
                                className="h-9 px-3"
                              >
                                <Folder className="w-3.5 h-3.5" />
                              </Button>
                            </div>
                          </div>
                        </CollapsibleContent>
                      </Collapsible>
                    </div>
                  </CardContent>
                </Card>
              )}

              {step === 'complete' && (
                <Card className="bg-card/50 border-border">
                  <CardContent className="p-8 space-y-6 text-center">
                    <div className="mx-auto w-14 h-14 rounded-full bg-chart-2 flex items-center justify-center">
                      <Check
                        className="w-7 h-7 text-primary-foreground"
                        strokeWidth={2.5}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                        You're all set
                      </h1>
                      <p className="text-sm text-muted-foreground">
                        SyftHub Desktop is configured and ready.
                      </p>
                    </div>
                    <Button
                      onClick={() => window.location.reload()}
                      className="w-full h-11"
                    >
                      Open Dashboard
                    </Button>
                  </CardContent>
                </Card>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
