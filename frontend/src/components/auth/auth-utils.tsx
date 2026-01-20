import React from 'react';

// Loading state for auth forms
export function AuthLoadingOverlay() {
  return (
    <div className='absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-white/80 backdrop-blur-sm'>
      <div className='text-syft-primary flex items-center gap-2'>
        <div className='border-syft-primary h-4 w-4 animate-spin rounded-full border-2 border-t-transparent'></div>
        <span className='font-inter text-sm'>Please wait…</span>
      </div>
    </div>
  );
}

// Error alert component for auth forms
interface AuthErrorAlertProperties {
  error: string;
  onDismiss?: () => void;
}

export function AuthErrorAlert({ error, onDismiss }: Readonly<AuthErrorAlertProperties>) {
  return (
    <div className='flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-3'>
      <div className='mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-red-500'>
        <div className='h-2 w-2 rounded-full bg-white'></div>
      </div>
      <div className='min-w-0 flex-1'>
        <p className='font-inter text-sm text-red-700'>{error}</p>
      </div>
      {onDismiss && (
        <button
          type='button'
          onClick={onDismiss}
          className='flex-shrink-0 text-red-400 transition-colors hover:text-red-600'
        >
          <span className='sr-only'>Dismiss</span>
          <div className='flex h-4 w-4 items-center justify-center'>×</div>
        </button>
      )}
    </div>
  );
}
