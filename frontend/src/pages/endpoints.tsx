import { ParticipateView } from '@/components/participate-view';

/**
 * Endpoints page - Guide users to participate in the network.
 * This is a protected route - requires authentication.
 */
export default function EndpointsPage() {
  return <ParticipateView title='Get Started with Endpoints' />;
}
