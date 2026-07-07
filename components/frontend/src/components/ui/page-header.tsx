import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  path?: string;
  children?: ReactNode;
}

export function PageHeader({ title, path, children }: Readonly<PageHeaderProps>) {
  return (
    <div className='border-border bg-background/95 sticky top-0 z-30 flex w-full items-center justify-between border-b px-6 py-4 backdrop-blur-sm'>
      <div className='flex items-center gap-4'>
        <h2 className='font-rubik text-foreground text-xl font-medium'>{title}</h2>
        {path ? (
          <div className='text-muted-foreground hidden font-mono text-xs opacity-60 sm:block'>
            {path}
          </div>
        ) : null}
      </div>
      {children}
    </div>
  );
}
