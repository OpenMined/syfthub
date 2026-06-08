import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowLeft, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { OpenMinedIcon } from '@/components/ui/openmined-icon';
import { useSettings } from '@/contexts/SettingsContext';
import {
  DEFAULT_SYFTHUB_URL,
  extractErrorMessage,
  isValidEmail,
  isValidUrl,
} from '@/lib/utils';
import {
  BrowseForFolder,
  StartEmailSignIn,
  VerifyEmailSignIn,
  ResendEmailSignIn,
} from '../../wailsjs/go/main/App';
import { WindowControls } from '@/components/ui/window-controls';
import { ErrorBanner } from '@/components/ui/error-banner';
import { OtpInput } from '@/components/onboarding/OtpInput';
import { AdvancedSettings } from '@/components/onboarding/AdvancedSettings';

const isMac = navigator.userAgent.includes('Macintosh');

type WizardStep = 'email' | 'otp' | 'complete';

const RESEND_COOLDOWN_SECONDS = 30;

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export function OnboardingWizard() {
  const { saveSettings, defaultEndpointsPath } = useSettings();

  const [step, setStep] = useState<WizardStep>('email');

  // Connection / advanced settings.
  const [syfthubUrl, setSyfthubUrl] = useState(DEFAULT_SYFTHUB_URL);
  const [endpointsPath, setEndpointsPath] = useState('');

  // Email sign-in.
  const [email, setEmail] = useState('');

  // OTP step.
  const [otpCode, setOtpCode] = useState('');
  const [resendCooldown, setResendCooldown] = useState(0);

  // Shared.
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [apiKeyBusy, setApiKeyBusy] = useState(false);

  const effectivePath = endpointsPath || defaultEndpointsPath || '.endpoints';
  const isUrlValid = isValidUrl(syfthubUrl);
  const hostname = safeHostname(syfthubUrl);
  const emailValid = isValidEmail(email);
  const canSend = isUrlValid && emailValid && !isBusy;

  // Resend cooldown ticker.
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const interval = window.setInterval(() => {
      setResendCooldown((s) => (s <= 1 ? 0 : s - 1));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [resendCooldown]);

  const handleBrowse = async () => {
    const path = await BrowseForFolder('Select Endpoints Directory');
    if (path) {
      setEndpointsPath(path);
    }
  };

  // ── Email → send code ──────────────────────────────────────────────────────
  const handleSendCode = async () => {
    if (!canSend) return;
    setIsBusy(true);
    setError(null);
    try {
      await StartEmailSignIn(syfthubUrl, email.trim(), effectivePath);
      setOtpCode('');
      setResendCooldown(RESEND_COOLDOWN_SECONDS);
      setStep('otp');
    } catch (err) {
      setError(extractErrorMessage(err, 'Failed to send sign-in code'));
    } finally {
      setIsBusy(false);
    }
  };

  // ── OTP ────────────────────────────────────────────────────────────────────
  const canVerify = otpCode.length === 6 && !isBusy;

  const handleVerify = async (codeOverride?: string) => {
    const code = codeOverride ?? otpCode;
    if (code.length !== 6) return;
    setIsBusy(true);
    setError(null);
    try {
      await VerifyEmailSignIn(code);
      setStep('complete');
    } catch (err) {
      setError(extractErrorMessage(err, 'Failed to verify code'));
    } finally {
      setIsBusy(false);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0 || isBusy) return;
    setError(null);
    // Start the cooldown immediately so a fast double-click can't fire a second
    // request before the await resolves; roll it back if the request fails.
    setResendCooldown(RESEND_COOLDOWN_SECONDS);
    try {
      await ResendEmailSignIn();
    } catch (err) {
      setResendCooldown(0);
      setError(extractErrorMessage(err, 'Failed to resend code'));
    }
  };

  const handleOtpBack = () => {
    setStep('email');
    setOtpCode('');
    setError(null);
  };

  // ── API-key escape hatch ─────────────────────────────────────────────────
  const handleUseApiKey = async (apiKey: string) => {
    if (!apiKey) return;
    setApiKeyBusy(true);
    setError(null);
    try {
      await saveSettings(syfthubUrl, apiKey, effectivePath);
      setStep('complete');
    } catch (err) {
      setError(extractErrorMessage(err, 'Failed to save settings'));
    } finally {
      setApiKeyBusy(false);
    }
  };

  return (
    <div
      className={`h-screen flex flex-col bg-gradient-to-br from-background via-card to-background text-foreground ${
        !isMac ? 'rounded-xl overflow-hidden shadow-2xl' : ''
      }`}
    >
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
              {step === 'email' && (
                <Card className="bg-card/50 border-border">
                  <CardContent className="p-8 space-y-7">
                    <div className="flex flex-col items-center text-center space-y-3">
                      <OpenMinedIcon className="w-12 h-12" />
                      <div className="space-y-1.5">
                        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                          Sign in to SyftHub
                        </h1>
                        <p className="text-sm text-muted-foreground">
                          Enter your email and we'll send you a sign-in code. No
                          password needed.
                        </p>
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <Label htmlFor="email" className="sr-only">
                        Email
                      </Label>
                      <Input
                        id="email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@example.com"
                        autoFocus
                        autoComplete="email"
                        spellCheck={false}
                        disabled={isBusy}
                        className={`h-12 ${
                          email && !emailValid
                            ? 'border-destructive focus-visible:border-destructive'
                            : ''
                        }`}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && canSend) handleSendCode();
                        }}
                      />
                    </div>

                    <ErrorBanner message={error} />

                    <Button
                      onClick={handleSendCode}
                      className="w-full h-11"
                      disabled={!canSend}
                    >
                      {isBusy ? 'Sending code…' : 'Send sign-in code'}
                    </Button>

                    <AdvancedSettings
                      syfthubUrl={syfthubUrl}
                      onSyfthubUrlChange={setSyfthubUrl}
                      endpointsPath={endpointsPath}
                      onEndpointsPathChange={setEndpointsPath}
                      defaultEndpointsPath={defaultEndpointsPath}
                      onBrowse={handleBrowse}
                      hostname={hostname}
                      disabled={isBusy}
                      onUseApiKey={handleUseApiKey}
                      apiKeyBusy={apiKeyBusy}
                    />
                  </CardContent>
                </Card>
              )}

              {step === 'otp' && (
                <Card className="bg-card/50 border-border">
                  <CardContent className="p-8 space-y-7">
                    <div className="flex flex-col items-center text-center space-y-3">
                      <OpenMinedIcon className="w-12 h-12" />
                      <div className="space-y-1.5">
                        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                          Check your email
                        </h1>
                        <p className="text-sm text-muted-foreground">
                          Enter the 6-digit code we sent to{' '}
                          <span className="text-foreground font-medium">
                            {email.trim()}
                          </span>
                          .
                        </p>
                      </div>
                    </div>

                    <OtpInput
                      value={otpCode}
                      onChange={setOtpCode}
                      onComplete={(code) => handleVerify(code)}
                      disabled={isBusy}
                      autoFocus
                    />

                    <ErrorBanner message={error} />

                    <div className="space-y-3">
                      <Button
                        onClick={() => handleVerify()}
                        className="w-full h-11"
                        disabled={!canVerify}
                      >
                        {isBusy ? 'Verifying…' : 'Verify & Continue'}
                      </Button>
                      <div className="flex items-center justify-between">
                        <button
                          type="button"
                          onClick={handleOtpBack}
                          disabled={isBusy}
                          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <ArrowLeft className="w-3.5 h-3.5" />
                          Use a different email
                        </button>
                        <button
                          type="button"
                          onClick={handleResend}
                          disabled={resendCooldown > 0 || isBusy}
                          className="text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {resendCooldown > 0
                            ? `Resend code in ${resendCooldown}s`
                            : 'Resend code'}
                        </button>
                      </div>
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
