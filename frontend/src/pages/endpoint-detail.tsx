import { useNavigate, useParams } from 'react-router-dom';

import { EndpointDetail } from '@/components/endpoint-detail';

/**
 * Endpoint Detail page - View details of a specific endpoint.
 * Uses GitHub-style URLs: /:username/:slug
 */
export default function EndpointDetailPage() {
  const { username, slug } = useParams<{ username: string; slug: string }>();
  const navigate = useNavigate();

  const handleBack = () => {
    // eslint-disable-next-line @typescript-eslint/no-floating-promises -- Navigation is fire-and-forget
    navigate('/browse');
  };

  // If no slug provided, show error state (handled by EndpointDetail)
  if (!slug) {
    return (
      <div className='flex min-h-[400px] items-center justify-center'>
        <p className='text-syft-muted'>Invalid endpoint URL</p>
      </div>
    );
  }

  return <EndpointDetail slug={slug} owner={username} onBack={handleBack} />;
}
