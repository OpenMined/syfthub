import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { OpenMinedIcon } from '@/components/ui/openmined-icon';
import { useSettings } from '@/contexts/SettingsContext';
import { BrowseForFolder } from '../../wailsjs/go/main/App';

type WizardStep = 'welcome' | 'configure' | 'complete';

const DEFAULT_SYFTHUB_URL = 'https://syfthub-dev.openmined.org';

export function OnboardingWizard() {
  const { saveSettings, defaultEndpointsPath, isLoading } = useSettings();
  const [step, setStep] = useState<WizardStep>('welcome');
  const [syfthubUrl, setSyfthubUrl] = useState(DEFAULT_SYFTHUB_URL);
  const [apiKey, setApiKey] = useState('');
  const [endpointsPath, setEndpointsPath] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Use default path when it becomes available
  const effectivePath = endpointsPath || defaultEndpointsPath || '.endpoints';

  const handleBrowse = async () => {
    const path = await BrowseForFolder('Select Endpoints Directory');
    if (path) {
      setEndpointsPath(path);
    }
  };

  const handleUseDefault = (field: 'url' | 'path') => {
    if (field === 'url') {
      setSyfthubUrl(DEFAULT_SYFTHUB_URL);
    } else {
      setEndpointsPath(defaultEndpointsPath);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await saveSettings(syfthubUrl, apiKey, effectivePath);
      setStep('complete');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setIsSaving(false);
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

  const isUrlValid = validateUrl(syfthubUrl);

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-card to-background flex items-center justify-center p-6">
      <div className="w-full max-w-lg">
        {/* Step Indicator */}
        <div className="flex items-center justify-center mb-8">
          <div className="flex items-center gap-2">
            {(['welcome', 'configure', 'complete'] as WizardStep[]).map((s, i) => (
              <div key={s} className="flex items-center">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                    step === s
                      ? 'bg-primary text-primary-foreground'
                      : ['welcome'].indexOf(step) < i
                      ? 'bg-secondary text-muted-foreground'
                      : 'bg-chart-2/20 text-chart-2'
                  }`}
                >
                  {i + 1}
                </div>
                {i < 2 && (
                  <div
                    className={`w-12 h-0.5 mx-1 ${
                      ['welcome', 'configure'].indexOf(step) >= i
                        ? 'bg-primary'
                        : 'bg-secondary'
                    }`}
                  />
                )}
              </div>
            ))}
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
          >

        {/* Welcome Step */}
        {step === 'welcome' && (
          <Card className="bg-card/50 border-border">
            <CardHeader className="text-center">
              <div className="mx-auto w-16 h-16 flex items-center justify-center mb-4">
                <OpenMinedIcon className="w-14 h-14" />
              </div>
              <CardTitle className="text-2xl text-foreground">Welcome to SyftHub Desktop</CardTitle>
              <CardDescription className="text-muted-foreground mt-2">
                Let's get you set up to run your local endpoints.
                This will only take a moment.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-3 text-sm text-secondary-foreground">
                <div className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-primary text-xs">1</span>
                  </div>
                  <p>Connect to a SyftHub server to sync your endpoints</p>
                </div>
                <div className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-primary text-xs">2</span>
                  </div>
                  <p>Choose where to store your endpoint files</p>
                </div>
                <div className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <span className="text-primary text-xs">3</span>
                  </div>
                  <p>Start managing your endpoints locally</p>
                </div>
              </div>
              <Button
                onClick={() => setStep('configure')}
                className="w-full"
                size="lg"
              >
                Get Started
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Configure Step */}
        {step === 'configure' && (
          <Card className="bg-card/50 border-border">
            <CardHeader>
              <CardTitle className="text-xl text-foreground">Configuration</CardTitle>
              <CardDescription className="text-muted-foreground">
                Set up your connection and storage settings
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* SyftHub URL */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="syfthubUrl" className="text-foreground">
                    SyftHub URL
                  </Label>
                  <button
                    type="button"
                    onClick={() => handleUseDefault('url')}
                    className="text-xs text-primary hover:text-primary/80"
                  >
                    Use Default
                  </button>
                </div>
                <Input
                  id="syfthubUrl"
                  type="url"
                  value={syfthubUrl}
                  onChange={(e) => setSyfthubUrl(e.target.value)}
                  placeholder="https://syfthub-dev.openmined.org"
                  className={syfthubUrl && !isUrlValid ? 'border-destructive focus:border-destructive' : ''}
                />
                {syfthubUrl && !isUrlValid && (
                  <p className="text-xs text-destructive">Please enter a valid URL</p>
                )}
              </div>

              {/* API Key (Optional) */}
              <div className="space-y-2">
                <Label htmlFor="apiKey" className="text-foreground">
                  API Key <span className="text-muted-foreground text-xs">(optional)</span>
                </Label>
                <Input
                  id="apiKey"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Enter your API key"
                />
              </div>

              {/* Endpoints Path */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor="endpointsPath" className="text-foreground">
                    Endpoints Directory
                  </Label>
                  <button
                    type="button"
                    onClick={() => handleUseDefault('path')}
                    className="text-xs text-primary hover:text-primary/80"
                  >
                    Use Default
                  </button>
                </div>
                <div className="flex gap-2">
                  <Input
                    id="endpointsPath"
                    type="text"
                    value={effectivePath}
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
                  This is where your endpoint files will be stored
                </p>
              </div>

              {error && (
                <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm">
                  {error}
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <Button
                  variant="outline"
                  onClick={() => setStep('welcome')}
                  className="flex-1"
                  disabled={isSaving}
                >
                  Back
                </Button>
                <Button
                  onClick={handleSave}
                  className="flex-1"
                  disabled={isSaving || !isUrlValid || !effectivePath}
                >
                  {isSaving ? 'Saving...' : 'Save & Continue'}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Complete Step */}
        {step === 'complete' && (
          <Card className="bg-card/50 border-border">
            <CardHeader className="text-center">
              <div className="mx-auto w-16 h-16 rounded-full bg-chart-2/20 flex items-center justify-center mb-4">
                <Check className="w-8 h-8 text-chart-2" strokeWidth={2} />
              </div>
              <CardTitle className="text-2xl text-foreground">You're All Set!</CardTitle>
              <CardDescription className="text-muted-foreground mt-2">
                SyftHub Desktop is configured and ready to use.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="bg-background/50 rounded-lg p-4 space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Server</span>
                  <span className="text-foreground font-mono text-xs truncate max-w-[200px]">
                    {syfthubUrl}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Endpoints</span>
                  <span className="text-foreground font-mono text-xs truncate max-w-[200px]">
                    {effectivePath}
                  </span>
                </div>
              </div>

              <p className="text-sm text-muted-foreground text-center">
                You can change these settings anytime from the Settings menu.
              </p>

              {/* The page will automatically refresh/redirect after settings are saved */}
              <Button
                onClick={() => window.location.reload()}
                className="w-full bg-chart-2 hover:bg-chart-2/90 text-primary-foreground"
                size="lg"
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
  );
}
