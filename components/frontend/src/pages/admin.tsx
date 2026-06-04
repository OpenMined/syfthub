import { AdminDashboard } from '@/components/admin/admin-dashboard';

/**
 * Admin dashboard page (`/admin`).
 *
 * Mounted behind `ProtectedRoute > RoleBasedRoute requiredRole="admin"`, so by
 * the time this renders the viewer is an authenticated admin. The page is pure
 * composition; the dashboard owns all data and state.
 */
export default function AdminPage() {
  return <AdminDashboard />;
}
