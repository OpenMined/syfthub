import type { RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';

import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AccountingProvider } from '@/context/accounting-context';
import { AuthProvider } from '@/context/auth-context';
import { ModalProvider } from '@/context/modal-context';
import { SettingsModalProvider } from '@/context/settings-modal-context';
import { ThemeProvider } from '@/context/theme-context';

/**
 * AllProviders wraps children in the same provider stack as app.tsx
 * (minus ErrorBoundary which would swallow test errors).
 */
function AllProviders({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <ThemeProvider defaultTheme='light'>
      <AuthProvider>
        <AccountingProvider>
          <ModalProvider>
            <SettingsModalProvider>
              <MemoryRouter>{children}</MemoryRouter>
            </SettingsModalProvider>
          </ModalProvider>
        </AccountingProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

/**
 * Custom render that wraps the component in all app providers.
 */
function renderWithProviders(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  return render(ui, { wrapper: AllProviders, ...options });
}

export { AllProviders, renderWithProviders };
