import type { RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AccountingProvider } from '@/context/accounting-context';
import { AuthProvider } from '@/context/auth-context';
import { ThemeProvider } from '@/context/theme-context';

/**
 * Create a fresh QueryClient for each test to prevent state leaking between tests.
 * Configured with no retries and immediate GC for faster test execution.
 */
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0
      },
      mutations: {
        retry: false
      }
    }
  });
}

/**
 * AllProviders wraps children in the same provider stack as app.tsx
 * (minus ErrorBoundary which would swallow test errors).
 * Modal and settings modal state is now managed by Zustand stores
 * and doesn't need provider wrapping.
 */
function AllProviders({ children }: Readonly<{ children: ReactNode }>) {
  const testQueryClient = createTestQueryClient();

  return (
    <QueryClientProvider client={testQueryClient}>
      <ThemeProvider defaultTheme='light'>
        <AuthProvider>
          <AccountingProvider>
            <MemoryRouter>{children}</MemoryRouter>
          </AccountingProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

/**
 * Custom render that wraps the component in all app providers.
 */
function renderWithProviders(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  return render(ui, { wrapper: AllProviders, ...options });
}

export { AllProviders, createTestQueryClient, renderWithProviders };
