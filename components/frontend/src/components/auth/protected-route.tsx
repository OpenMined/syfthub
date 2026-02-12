import type React from 'react';

import { Navigate, useLocation } from 'react-router-dom';

import { useAuth } from '@/context/auth-context';

import { LoadingSpinner } from '../ui/loading-spinner';

interface ProtectedRouteProperties {
  children: React.ReactNode;
  redirectTo?: string;
}

/**
 * ProtectedRoute - Wraps routes that require authentication.
 *
 * If the user is not authenticated, they are redirected to the specified
 * route (default: "/") with the attempted location stored in state.
 * This allows redirecting back after successful login.
 *
 * Usage:
 * ```tsx
 * <Route path="/profile" element={
 *   <ProtectedRoute>
 *     <ProfilePage />
 *   </ProtectedRoute>
 * } />
 * ```
 */
export function ProtectedRoute({ children, redirectTo = '/' }: Readonly<ProtectedRouteProperties>) {
  const { user, isInitializing } = useAuth();
  const location = useLocation();

  // Show loading spinner while checking authentication status
  if (isInitializing) {
    return (
      <div className='flex h-full min-h-[400px] items-center justify-center'>
        <LoadingSpinner size='lg' message='Loading…' />
      </div>
    );
  }

  // Redirect unauthenticated users, storing the attempted location
  if (!user) {
    return <Navigate to={redirectTo} state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
