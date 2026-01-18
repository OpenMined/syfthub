import React, { Component } from 'react';

import type { ErrorInfo, ReactNode } from 'react';

import { getOrCreateCorrelationId } from './correlation';
import { logger } from './logger';
import { reportError } from './reporter';

/**
 * React Error Boundary with error reporting.
 *
 * Catches JavaScript errors in child components and reports them
 * to the backend for logging and analysis.
 */

/** Props for the fallback component */
export interface ErrorFallbackProps {
  /** The error that was caught */
  error: Error;
  /** Correlation ID for support reference */
  correlationId: string;
  /** Function to attempt recovery */
  resetError: () => void;
}

/** Props for ErrorBoundary component */
export interface ErrorBoundaryProps {
  /** Child components to render */
  children: ReactNode;
  /** Custom fallback component */
  fallback?: React.ComponentType<ErrorFallbackProps>;
  /** Called when an error is caught */
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  /** Relevant app state to include in error report */
  appState?: Record<string, unknown>;
}

/** State for ErrorBoundary */
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  correlationId: string | null;
}

/**
 * Default error fallback UI.
 */
function DefaultErrorFallback(props: Readonly<ErrorFallbackProps>): React.JSX.Element {
  const { error, correlationId, resetError } = props;
  return (
    <div
      role='alert'
      style={{
        padding: '2rem',
        margin: '1rem',
        borderRadius: '0.5rem',
        backgroundColor: '#fee2e2',
        border: '1px solid #ef4444',
        color: '#991b1b'
      }}
    >
      <h2 style={{ margin: '0 0 1rem 0', fontSize: '1.25rem', fontWeight: 600 }}>
        Something went wrong
      </h2>
      <p style={{ margin: '0 0 1rem 0' }}>
        We apologize for the inconvenience. An error has occurred and has been reported.
      </p>
      <details style={{ marginBottom: '1rem' }}>
        <summary style={{ cursor: 'pointer', fontWeight: 500 }}>Error details</summary>
        <pre
          style={{
            marginTop: '0.5rem',
            padding: '0.5rem',
            backgroundColor: '#fef2f2',
            borderRadius: '0.25rem',
            fontSize: '0.875rem',
            overflow: 'auto',
            maxHeight: '200px'
          }}
        >
          {error.message}
        </pre>
      </details>
      <p style={{ margin: '0 0 1rem 0', fontSize: '0.875rem' }}>
        Reference ID: <code>{correlationId}</code>
      </p>
      <button
        onClick={resetError}
        style={{
          padding: '0.5rem 1rem',
          backgroundColor: '#ef4444',
          color: 'white',
          border: 'none',
          borderRadius: '0.25rem',
          cursor: 'pointer',
          fontWeight: 500
        }}
      >
        Try again
      </button>
    </div>
  );
}

/**
 * Error Boundary component that catches JavaScript errors in child components.
 *
 * Features:
 * - Catches and reports errors to backend
 * - Displays fallback UI
 * - Includes correlation ID for support reference
 * - Allows custom fallback components
 *
 * @example
 * <ErrorBoundary
 *   fallback={CustomErrorFallback}
 *   onError={(error) => console.error(error)}
 * >
 *   <App />
 * </ErrorBoundary>
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      correlationId: null
    };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return {
      hasError: true,
      error,
      correlationId: getOrCreateCorrelationId()
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    const { onError, appState } = this.props;

    // Log the error
    logger.error(
      'react.error.boundary',
      {
        componentStack: errorInfo.componentStack
      },
      error
    );

    // Report to backend
    reportError(
      error,
      'frontend.react.error_boundary',
      errorInfo.componentStack ?? undefined,
      appState
    ).catch(() => {
      // Ignore reporting errors
    });

    // Call custom error handler if provided
    if (onError) {
      onError(error, errorInfo);
    }
  }

  resetError = (): void => {
    this.setState({
      hasError: false,
      error: null,
      correlationId: null
    });
  };

  render(): React.JSX.Element {
    const { hasError, error, correlationId } = this.state;
    const { children, fallback: FallbackComponent } = this.props;

    if (hasError && error && correlationId) {
      if (FallbackComponent) {
        return (
          <FallbackComponent
            error={error}
            correlationId={correlationId}
            resetError={this.resetError}
          />
        );
      }

      return (
        <DefaultErrorFallback
          error={error}
          correlationId={correlationId}
          resetError={this.resetError}
        />
      );
    }

    return <>{children}</>;
  }
}
