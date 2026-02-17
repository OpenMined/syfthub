import { Component, Suspense } from 'react';

import type { ReactNode } from 'react';

import { LoadingSpinner } from '@/components/ui/loading-spinner';

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

interface RouteErrorBoundaryProps {
  children: ReactNode;
}

class RouteErrorBoundary extends Component<RouteErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: RouteErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className='flex min-h-[400px] flex-col items-center justify-center gap-4 p-8'>
          <div className='bg-destructive/10 flex h-16 w-16 items-center justify-center rounded-full'>
            <span className='text-destructive text-2xl'>!</span>
          </div>
          <h2 className='font-rubik text-foreground text-xl font-semibold'>Something went wrong</h2>
          <p className='text-muted-foreground max-w-md text-center text-sm'>
            {this.state.error?.message ?? 'An unexpected error occurred while loading this page.'}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
            }}
            className='bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm transition-colors'
          >
            Try again
          </button>
        </div>
      );
    }

    return <>{this.props.children}</>;
  }
}

interface RouteBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

export function RouteBoundary({ children, fallback }: Readonly<RouteBoundaryProps>) {
  return (
    <RouteErrorBoundary>
      <Suspense
        fallback={
          fallback ?? (
            <div className='flex min-h-[400px] items-center justify-center'>
              <LoadingSpinner size='lg' message='Loading…' />
            </div>
          )
        }
      >
        {children}
      </Suspense>
    </RouteErrorBoundary>
  );
}
