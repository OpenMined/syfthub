/**
 * CLI Setup Page — /cli-setup?port=PORT&state=STATE
 *
 * Opened by `syft node init` when no API token is configured.
 * Handles authentication (login or register) and API token creation,
 * then delivers the token back to the waiting CLI via a localhost redirect.
 *
 * This page is intentionally standalone — no MainLayout, sidebar, or navbar.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { APITokenCreateResponse } from '@/lib/sdk-client';

import { motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';
import Key from 'lucide-react/dist/esm/icons/key';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Terminal from 'lucide-react/dist/esm/icons/terminal';
import { useSearchParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/context/auth-context';
import { syftClient } from '@/lib/sdk-client';
import { getPasswordStrengthInfo } from '@/lib/validation';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PagePhase =
  | 'loading'
  | 'invalid'
  | 'auth'
  | 'verify-otp'
  | 'create-token'
  | 'delivering'
  | 'done'
  | 'error';

type AuthTab = 'login' | 'register';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function defaultTokenName(): string {
  const today = new Date().toISOString().slice(0, 10);
  return `syft-cli-${today}`;
}

function deliverTokenToCLI(token: string, port: string, state: string): void {
  const url = `http://127.0.0.1:${port}/cli/done?token=${encodeURIComponent(token)}&state=${encodeURIComponent(state)}`;
  globalThis.location.href = url;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PageHeader() {
  return (
    <div className='mb-8 flex flex-col items-center gap-2'>
      <div className='mb-1 flex items-center gap-2'>
        <div className='flex h-8 w-8 items-center justify-center rounded-lg bg-white/10'>
          <Terminal className='h-4 w-4 text-white/80' aria-hidden='true' />
        </div>
        <span className='font-rubik text-foreground text-lg font-semibold'>SyftHub</span>
      </div>
      <span className='font-inter text-muted-foreground rounded-full border border-white/10 bg-white/5 px-3 py-0.5 text-xs'>
        CLI Setup
      </span>
    </div>
  );
}

interface CardProps {
  children: React.ReactNode;
}
function Card({ children }: Readonly<CardProps>) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', duration: 0.4, bounce: 0.15 }}
      className='border-border bg-card w-full max-w-md rounded-2xl border p-8 shadow-2xl'
    >
      {children}
    </motion.div>
  );
}

interface ErrorAlertProps {
  message: string;
  onDismiss?: () => void;
}
function ErrorAlert({ message, onDismiss }: Readonly<ErrorAlertProps>) {
  if (!message) return null;
  return (
    <div className='flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm dark:border-red-800 dark:bg-red-950'>
      <AlertCircle
        className='mt-0.5 h-4 w-4 shrink-0 text-red-600 dark:text-red-400'
        aria-hidden='true'
      />
      <div className='flex-1'>
        <span className='text-red-800 dark:text-red-200'>{message}</span>
      </div>
      {onDismiss ? (
        <button
          type='button'
          onClick={onDismiss}
          className='text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300'
          aria-label='Dismiss error'
        >
          ×
        </button>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase: loading
// ---------------------------------------------------------------------------

function LoadingPhase() {
  return (
    <Card>
      <div className='flex flex-col items-center gap-4 py-8'>
        <Loader2 className='text-muted-foreground h-8 w-8 animate-spin' aria-hidden='true' />
        <p className='text-muted-foreground text-sm'>Connecting…</p>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Phase: invalid
// ---------------------------------------------------------------------------

function InvalidPhase() {
  return (
    <Card>
      <div className='flex flex-col items-center gap-4 py-4 text-center'>
        <div className='flex h-12 w-12 items-center justify-center rounded-full border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950'>
          <AlertCircle className='h-6 w-6 text-red-600 dark:text-red-400' aria-hidden='true' />
        </div>
        <div>
          <h2 className='text-foreground mb-1 text-lg font-semibold'>Invalid setup link</h2>
          <p className='text-muted-foreground text-sm'>
            This link is missing required parameters.
            <br />
            Please run{' '}
            <code className='bg-muted rounded px-1 font-mono text-xs'>syft node init</code> again to
            get a fresh link.
          </p>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Phase: error
// ---------------------------------------------------------------------------

interface ErrorPhaseProps {
  message: string;
}
function ErrorPhase({ message }: Readonly<ErrorPhaseProps>) {
  return (
    <Card>
      <div className='flex flex-col items-center gap-4 py-4 text-center'>
        <div className='flex h-12 w-12 items-center justify-center rounded-full border border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950'>
          <AlertCircle className='h-6 w-6 text-red-600 dark:text-red-400' aria-hidden='true' />
        </div>
        <div>
          <h2 className='text-foreground mb-1 text-lg font-semibold'>Something went wrong</h2>
          <p className='text-muted-foreground text-sm'>{message}</p>
          <p className='text-muted-foreground mt-2 text-xs'>
            Run <code className='bg-muted rounded px-1 font-mono'>syft node init</code> again to
            retry.
          </p>
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Phase: delivering / done
// ---------------------------------------------------------------------------

function DeliveringPhase() {
  return (
    <Card>
      <div className='flex flex-col items-center gap-4 py-8 text-center'>
        <Loader2 className='text-muted-foreground h-8 w-8 animate-spin' aria-hidden='true' />
        <div>
          <p className='text-foreground font-medium'>Sending token to CLI…</p>
          <p className='text-muted-foreground mt-1 text-sm'>
            Your terminal will resume automatically.
          </p>
        </div>
      </div>
    </Card>
  );
}

function DonePhase() {
  return (
    <Card>
      <div className='flex flex-col items-center gap-4 py-4 text-center'>
        <div className='flex h-12 w-12 items-center justify-center rounded-full border border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900'>
          <Check className='h-6 w-6 text-green-600 dark:text-green-400' aria-hidden='true' />
        </div>
        <div>
          <h2 className='text-foreground mb-1 text-lg font-semibold'>All set!</h2>
          <p className='text-muted-foreground text-sm'>
            Your token was sent to the CLI.
            <br />
            Return to your terminal to continue.
          </p>
        </div>
        <Button
          variant='outline'
          size='sm'
          onClick={() => {
            window.close();
          }}
        >
          Close tab
        </Button>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Phase: create-token (authenticated user)
// ---------------------------------------------------------------------------

interface CreateTokenPhaseProps {
  username: string;
  tokenName: string;
  onTokenNameChange: (name: string) => void;
  onSubmit: () => void;
  isSubmitting: boolean;
  error: string;
  onDismissError: () => void;
}

function CreateTokenPhase({
  username,
  tokenName,
  onTokenNameChange,
  onSubmit,
  isSubmitting,
  error,
  onDismissError
}: Readonly<CreateTokenPhaseProps>) {
  return (
    <Card>
      <div className='mb-6'>
        <div className='text-muted-foreground mb-4 flex items-center gap-2 text-sm'>
          <div className='bg-primary/10 text-primary flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold'>
            {username.charAt(0).toUpperCase()}
          </div>
          <span>
            Signed in as <strong className='text-foreground'>@{username}</strong>
          </span>
        </div>
        <h2 className='text-foreground text-xl font-semibold'>Create CLI token</h2>
        <p className='text-muted-foreground mt-1 text-sm'>
          This token grants the CLI access to your account without your password.
        </p>
      </div>

      <div className='space-y-5'>
        <ErrorAlert message={error} onDismiss={onDismissError} />

        <div className='space-y-2'>
          <label htmlFor='cli-token-name' className='text-foreground text-sm font-medium'>
            Token name
          </label>
          <Input
            id='cli-token-name'
            value={tokenName}
            onChange={(e) => {
              onTokenNameChange(e.target.value);
            }}
            placeholder='e.g. syft-cli-2026-03-30'
            disabled={isSubmitting}
            maxLength={100}
            autoFocus
          />
          <p className='text-muted-foreground text-xs'>
            You can rename or revoke this token later in Settings → API Tokens.
          </p>
        </div>

        <div className='flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-3 dark:border-blue-800 dark:bg-blue-950'>
          <Key
            className='mt-0.5 h-4 w-4 shrink-0 text-blue-600 dark:text-blue-400'
            aria-hidden='true'
          />
          <p className='text-xs text-blue-800 dark:text-blue-200'>
            <strong>Full access · 1-year expiry</strong> — recommended for CLI use. You can create a
            scoped token from Settings any time.
          </p>
        </div>

        <Button
          className='w-full'
          size='lg'
          onClick={onSubmit}
          disabled={isSubmitting || !tokenName.trim()}
        >
          {isSubmitting ? (
            <>
              <Loader2 className='mr-2 h-4 w-4 animate-spin' aria-hidden='true' />
              Creating…
            </>
          ) : (
            <>
              <Key className='mr-2 h-4 w-4' aria-hidden='true' />
              Create token & return to terminal
            </>
          )}
        </Button>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Phase: auth (unauthenticated — login + register tabs)
// ---------------------------------------------------------------------------

interface LoginFormProps {
  onSuccess: () => void;
  onSwitchToRegister: () => void;
}

function LoginForm({ onSuccess, onSwitchToRegister }: Readonly<LoginFormProps>) {
  const { login, isLoading, error, clearError } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState('');

  const displayError = error ?? localError;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError('');
    if (!email.trim() || !password) {
      setLocalError('Email and password are required.');
      return;
    }
    try {
      await login({ email: email.trim(), password });
      onSuccess();
    } catch {
      // error is set by auth context
    }
  };

  return (
    <form onSubmit={handleSubmit} className='space-y-4'>
      <ErrorAlert
        message={displayError ?? ''}
        onDismiss={() => {
          clearError();
          setLocalError('');
        }}
      />

      <Input
        type='email'
        label='Email'
        placeholder='name@example.com'
        value={email}
        onChange={(e) => {
          setEmail(e.target.value);
          clearError();
        }}
        autoComplete='email'
        disabled={isLoading}
        isRequired
        autoFocus
      />
      <Input
        type='password'
        label='Password'
        placeholder='Enter your password'
        value={password}
        onChange={(e) => {
          setPassword(e.target.value);
          clearError();
        }}
        autoComplete='current-password'
        disabled={isLoading}
        isRequired
      />

      <Button
        type='submit'
        className='w-full'
        size='lg'
        disabled={isLoading || !email || !password}
      >
        {isLoading ? (
          <>
            <Loader2 className='mr-2 h-4 w-4 animate-spin' aria-hidden='true' />
            Signing in…
          </>
        ) : (
          'Sign In'
        )}
      </Button>

      <p className='text-muted-foreground text-center text-sm'>
        Don't have an account?{' '}
        <button
          type='button'
          onClick={onSwitchToRegister}
          className='text-foreground font-medium underline underline-offset-2 hover:no-underline'
          disabled={isLoading}
        >
          Create one
        </button>
      </p>
    </form>
  );
}

interface RegisterFormProps {
  onSuccess: (email: string) => void;
  onSwitchToLogin: () => void;
}

function RegisterForm({ onSuccess, onSwitchToLogin }: Readonly<RegisterFormProps>) {
  const { register: authRegister, isLoading, error, clearError } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState('');

  const displayError = error ?? localError;
  const strengthInfo = getPasswordStrengthInfo(password);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError('');

    if (!name.trim() || !email.trim() || !password) {
      setLocalError('All fields are required.');
      return;
    }
    if (password.length < 8) {
      setLocalError('Password must be at least 8 characters.');
      return;
    }

    try {
      const result = await authRegister({ name: name.trim(), email: email.trim(), password });
      if (result.requiresEmailVerification) {
        onSuccess(email.trim());
      } else {
        onSuccess('');
      }
    } catch {
      // error is set by auth context
    }
  };

  return (
    <form onSubmit={handleSubmit} className='space-y-4'>
      <ErrorAlert
        message={displayError ?? ''}
        onDismiss={() => {
          clearError();
          setLocalError('');
        }}
      />

      <Input
        type='text'
        label='Full name'
        placeholder='Jane Doe'
        value={name}
        onChange={(e) => {
          setName(e.target.value);
          clearError();
        }}
        autoComplete='name'
        disabled={isLoading}
        isRequired
        autoFocus
      />
      <Input
        type='email'
        label='Email'
        placeholder='name@example.com'
        value={email}
        onChange={(e) => {
          setEmail(e.target.value);
          clearError();
        }}
        autoComplete='email'
        disabled={isLoading}
        isRequired
      />

      <div className='space-y-1.5'>
        <Input
          type='password'
          label='Password'
          placeholder='Create a secure password'
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            clearError();
          }}
          autoComplete='new-password'
          disabled={isLoading}
          isRequired
        />
        {password ? (
          <div className='flex items-center gap-2'>
            <div className='bg-muted h-1.5 flex-1 overflow-hidden rounded-full'>
              <div
                className={`h-full transition-[width] duration-300 ${strengthInfo.color}`}
                style={{ width: `${String((strengthInfo.score / 5) * 100)}%` }}
              />
            </div>
            <span className='text-muted-foreground w-12 text-right text-xs'>
              {strengthInfo.label}
            </span>
          </div>
        ) : null}
      </div>

      <Button
        type='submit'
        className='w-full'
        size='lg'
        disabled={isLoading || !name || !email || !password}
      >
        {isLoading ? (
          <>
            <Loader2 className='mr-2 h-4 w-4 animate-spin' aria-hidden='true' />
            Creating account…
          </>
        ) : (
          'Create Account & Continue →'
        )}
      </Button>

      <p className='text-muted-foreground text-center text-xs'>
        By creating an account you agree to our{' '}
        <a
          href='/terms'
          target='_blank'
          rel='noreferrer'
          className='text-foreground underline underline-offset-2 hover:no-underline'
        >
          Terms
        </a>{' '}
        and{' '}
        <a
          href='/privacy'
          target='_blank'
          rel='noreferrer'
          className='text-foreground underline underline-offset-2 hover:no-underline'
        >
          Privacy Policy
        </a>
        .
      </p>

      <p className='text-muted-foreground text-center text-sm'>
        Already have an account?{' '}
        <button
          type='button'
          onClick={onSwitchToLogin}
          className='text-foreground font-medium underline underline-offset-2 hover:no-underline'
          disabled={isLoading}
        >
          Sign in
        </button>
      </p>
    </form>
  );
}

interface AuthPhaseProps {
  tab: AuthTab;
  onTabChange: (tab: AuthTab) => void;
  onLoginSuccess: () => void;
  onRegisterSuccess: (email: string) => void;
}

function AuthPhase({
  tab,
  onTabChange,
  onLoginSuccess,
  onRegisterSuccess
}: Readonly<AuthPhaseProps>) {
  return (
    <Card>
      <div className='mb-6'>
        <h2 className='text-foreground text-xl font-semibold'>Set up syft CLI</h2>
        <p className='text-muted-foreground mt-1 text-sm'>
          Sign in or create an account to generate your access token.
        </p>
      </div>

      {/* Tab switcher */}
      <div className='mb-6 flex rounded-lg border p-1'>
        {(['login', 'register'] as const).map((t) => (
          <button
            key={t}
            type='button'
            onClick={() => {
              onTabChange(t);
            }}
            className={[
              'flex-1 rounded-md py-1.5 text-sm font-medium transition-colors',
              tab === t
                ? 'bg-card text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            ].join(' ')}
          >
            {t === 'login' ? 'Sign in' : 'Create account'}
          </button>
        ))}
      </div>

      {tab === 'login' ? (
        <LoginForm
          onSuccess={onLoginSuccess}
          onSwitchToRegister={() => {
            onTabChange('register');
          }}
        />
      ) : (
        <RegisterForm
          onSuccess={onRegisterSuccess}
          onSwitchToLogin={() => {
            onTabChange('login');
          }}
        />
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Phase: verify-otp
// ---------------------------------------------------------------------------

interface VerifyOtpPhaseProps {
  email: string;
  onSuccess: () => void;
}

function VerifyOtpPhase({ email, onSuccess }: Readonly<VerifyOtpPhaseProps>) {
  const { verifyOtp, resendOtp, isLoading, error, clearError } = useAuth();
  const [code, setCode] = useState('');
  const [resendSent, setResendSent] = useState(false);
  const [localError, setLocalError] = useState('');

  const displayError = error ?? localError;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError('');
    if (code.trim().length < 4) {
      setLocalError('Please enter the verification code.');
      return;
    }
    try {
      await verifyOtp(email, code.trim());
      onSuccess();
    } catch {
      // error set by auth context
    }
  };

  const handleResend = async () => {
    try {
      await resendOtp(email);
      setResendSent(true);
      setTimeout(() => {
        setResendSent(false);
      }, 4000);
    } catch {
      // ignore
    }
  };

  return (
    <Card>
      <div className='mb-6'>
        <h2 className='text-foreground text-xl font-semibold'>Verify your email</h2>
        <p className='text-muted-foreground mt-1 text-sm'>
          We sent a verification code to <strong className='text-foreground'>{email}</strong>.
        </p>
      </div>

      <form onSubmit={handleSubmit} className='space-y-4'>
        <ErrorAlert
          message={displayError ?? ''}
          onDismiss={() => {
            clearError();
            setLocalError('');
          }}
        />

        <Input
          type='text'
          label='Verification code'
          placeholder='Enter code…'
          value={code}
          onChange={(e) => {
            setCode(e.target.value);
            clearError();
          }}
          inputMode='numeric'
          autoComplete='one-time-code'
          disabled={isLoading}
          isRequired
          autoFocus
          maxLength={8}
        />

        <Button type='submit' className='w-full' size='lg' disabled={isLoading || !code.trim()}>
          {isLoading ? (
            <>
              <Loader2 className='mr-2 h-4 w-4 animate-spin' aria-hidden='true' />
              Verifying…
            </>
          ) : (
            'Verify & Continue →'
          )}
        </Button>

        <p className='text-muted-foreground text-center text-sm'>
          Didn't receive it?{' '}
          <button
            type='button'
            onClick={handleResend}
            className='text-foreground font-medium underline underline-offset-2 hover:no-underline disabled:opacity-50'
            disabled={isLoading || resendSent}
          >
            {resendSent ? 'Sent!' : 'Resend code'}
          </button>
        </p>
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function CLISetupPage() {
  const [searchParams] = useSearchParams();
  const { user, isInitializing } = useAuth();

  const port = searchParams.get('port');
  const state = searchParams.get('state');

  const [phase, setPhase] = useState<PagePhase>('loading');
  const [authTab, setAuthTab] = useState<AuthTab>('login');
  const [pendingEmail, setPendingEmail] = useState('');
  const [tokenName, setTokenName] = useState(defaultTokenName);
  const [isCreatingToken, setIsCreatingToken] = useState(false);
  const [tokenError, setTokenError] = useState('');

  // Prevents double-navigation to the token phase when auth fires multiple times.
  const hasNavigatedToTokenRef = useRef(false);
  // Guards against concurrent token-creation requests.
  const inFlightRef = useRef(false);
  // Holds the fallback "done" timer so it can be cleared on unmount.
  const doneTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Validate URL params
  const paramsValid = Boolean(port && state && /^\d+$/.test(port));

  // Transition from loading → appropriate phase once auth context is ready.
  // Only acts while still in the 'loading' phase so a background re-fetch
  // (which produces a new user object reference) doesn't reset an in-progress flow.
  useEffect(() => {
    if (isInitializing) return;

    if (!paramsValid) {
      setPhase('invalid');
      return;
    }

    if (user) {
      setPhase((prev) => (prev === 'loading' ? 'create-token' : prev));
    } else {
      setPhase((prev) => (prev === 'loading' ? 'auth' : prev));
    }
  }, [isInitializing, paramsValid, user]);

  // Clear the fallback redirect timer if the component unmounts mid-flow.
  useEffect(() => {
    return () => {
      if (doneTimerRef.current !== null) clearTimeout(doneTimerRef.current);
    };
  }, []);

  // Create token and deliver to CLI
  const createAndDeliver = useCallback(
    async (name: string) => {
      if (!port || !state || inFlightRef.current) return;
      inFlightRef.current = true;
      setIsCreatingToken(true);
      setTokenError('');

      try {
        const expiresAt = new Date(Date.now() + 365 * 86_400_000); // 1 year
        const response: APITokenCreateResponse = await syftClient.apiTokens.create({
          name: name.trim() || defaultTokenName(),
          scopes: ['full'],
          expiresAt
        });

        setPhase('delivering');
        // Brief pause so the user sees "Sending…" before the redirect
        await new Promise<void>((resolve) => {
          setTimeout(resolve, 600);
        });
        deliverTokenToCLI(response.token, port, state);
        // If redirect didn't navigate away (popup blocker etc.), show done state
        doneTimerRef.current = setTimeout(() => {
          setPhase('done');
        }, 2000);
      } catch (error) {
        inFlightRef.current = false;
        setIsCreatingToken(false);
        setTokenError(
          error instanceof Error ? error.message : 'Failed to create token. Please try again.'
        );
      }
    },
    [port, state]
  );

  // After login/register succeeds, navigate to the token-creation confirmation phase.
  const handleAuthSuccess = useCallback(() => {
    if (hasNavigatedToTokenRef.current) return;
    hasNavigatedToTokenRef.current = true;
    setPhase('create-token');
  }, []);

  const handleRegisterSuccess = useCallback(
    (email: string) => {
      if (email) {
        // Email verification required
        setPendingEmail(email);
        setPhase('verify-otp');
      } else {
        // No verification needed — go straight to token creation
        handleAuthSuccess();
      }
    },
    [handleAuthSuccess]
  );

  const renderPhase = () => {
    switch (phase) {
      case 'loading': {
        return <LoadingPhase />;
      }
      case 'invalid': {
        return <InvalidPhase />;
      }
      case 'error': {
        return <ErrorPhase message={tokenError || 'An unexpected error occurred.'} />;
      }
      case 'auth': {
        return (
          <AuthPhase
            tab={authTab}
            onTabChange={setAuthTab}
            onLoginSuccess={handleAuthSuccess}
            onRegisterSuccess={handleRegisterSuccess}
          />
        );
      }
      case 'verify-otp': {
        return <VerifyOtpPhase email={pendingEmail} onSuccess={handleAuthSuccess} />;
      }
      case 'create-token': {
        return (
          <CreateTokenPhase
            username={user?.username ?? ''}
            tokenName={tokenName}
            onTokenNameChange={setTokenName}
            onSubmit={() => {
              void createAndDeliver(tokenName);
            }}
            isSubmitting={isCreatingToken}
            error={tokenError}
            onDismissError={() => {
              setTokenError('');
            }}
          />
        );
      }
      case 'delivering': {
        return <DeliveringPhase />;
      }
      case 'done': {
        return <DonePhase />;
      }
    }
  };

  return (
    <div className='bg-background flex min-h-screen flex-col items-center justify-center px-4 py-12'>
      <PageHeader />
      {renderPhase()}
      <p className='text-muted-foreground mt-8 text-xs'>
        SyftHub ·{' '}
        <a
          href='/'
          className='hover:text-foreground underline underline-offset-2'
          target='_blank'
          rel='noreferrer'
        >
          syfthub.openmined.org
        </a>
      </p>
    </div>
  );
}
