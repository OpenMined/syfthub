import type { PropsWithChildren } from 'react';

import { ModalProvider } from '@/context/modal-context';
import { SettingsModalProvider } from '@/context/settings-modal-context';
import { ThemeProvider } from '@/context/theme-context';

type TRootProvider = PropsWithChildren;

/**
 * RootProvider - Composes all UI-concern providers (theme, modals).
 *
 * These providers manage UI state that is independent of auth/data layers.
 * Consolidating them here reduces nesting depth in the app root.
 */
export default function RootProvider({ children }: Readonly<TRootProvider>) {
  return (
    <ThemeProvider defaultTheme='system'>
      <ModalProvider>
        <SettingsModalProvider>{children}</SettingsModalProvider>
      </ModalProvider>
    </ThemeProvider>
  );
}
