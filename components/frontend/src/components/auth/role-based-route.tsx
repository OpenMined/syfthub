import type { UserRole } from '@/lib/types';
import type React from 'react';

import ShieldAlert from 'lucide-react/dist/esm/icons/shield-alert';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/auth-context';

import { LoadingSpinner } from '../ui/loading-spinner';

interface RoleBasedRouteProperties {
  children: React.ReactNode;
  /** Role the current user must have to view the wrapped route. */
  requiredRole: UserRole;
  /** Optional override for the access-denied state. */
  fallback?: React.ReactNode;
}

/**
 * Access-denied state shown to authenticated users who lack the required role.
 *
 * Rendered in-page rather than redirecting so a deep-linked admin URL gives
 * clear feedback instead of bouncing the user somewhere unexpected. This is a
 * UX affordance only — the backend `require_admin` dependency is the real
 * authorization boundary.
 */
function AccessDenied() {
  return (
    <div className='flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center'>
      <div className='bg-muted text-muted-foreground flex size-14 items-center justify-center rounded-full'>
        <ShieldAlert className='size-7' aria-hidden='true' />
      </div>
      <h1 className='text-foreground text-2xl font-semibold'>Access denied</h1>
      <p className='text-muted-foreground max-w-md text-sm'>
        You don&apos;t have permission to view this page. This area is restricted to administrators.
      </p>
      <Button asChild variant='outline'>
        <Link to='/'>Back to home</Link>
      </Button>
    </div>
  );
}

/**
 * RoleBasedRoute — wraps routes that require a specific user role.
 *
 * While auth is still initializing it shows a spinner. If the user is missing
 * or has the wrong role, it renders the access-denied state (or a supplied
 * `fallback`). Wrap inside `ProtectedRoute` so unauthenticated users are
 * redirected to sign in before the role check runs.
 *
 * Usage:
 * ```tsx
 * <Route path="admin" element={
 *   <ProtectedRoute>
 *     <RoleBasedRoute requiredRole="admin">
 *       <AdminPage />
 *     </RoleBasedRoute>
 *   </ProtectedRoute>
 * } />
 * ```
 */
export function RoleBasedRoute({
  children,
  requiredRole,
  fallback
}: Readonly<RoleBasedRouteProperties>) {
  const { user, isInitializing } = useAuth();

  if (isInitializing) {
    return (
      <div className='flex h-full min-h-[400px] items-center justify-center'>
        <LoadingSpinner size='lg' message='Loading…' />
      </div>
    );
  }

  if (user?.role !== requiredRole) {
    return <>{fallback ?? <AccessDenied />}</>;
  }

  return <>{children}</>;
}
