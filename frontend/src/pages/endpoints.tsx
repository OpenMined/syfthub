import { EndpointManagement } from '@/components/endpoint-management';

/**
 * Endpoints page - Manage user's data endpoints.
 * This is a protected route - requires authentication.
 */
export default function EndpointsPage() {
  return <EndpointManagement />;
}
