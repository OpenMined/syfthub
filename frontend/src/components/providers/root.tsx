import type { PropsWithChildren } from 'react';

type TRootProvider = PropsWithChildren;

export default function RootProvider({ children }: Readonly<TRootProvider>) {
  return <>{children}</>;
}
