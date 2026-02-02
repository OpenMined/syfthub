import type { PropsWithChildren } from 'react';

import { ThemeProvider } from '@/context/theme-context';

type TRootProvider = PropsWithChildren;

export default function RootProvider({ children }: Readonly<TRootProvider>) {
  return <ThemeProvider defaultTheme='system'>{children}</ThemeProvider>;
}
