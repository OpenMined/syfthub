/**
 * Agent page at route /agent/:owner/:slug
 */
import { useParams } from 'react-router-dom';

import { AgentView } from '@/components/agent/agent-view';

export default function AgentPage() {
  const { owner, slug } = useParams<{ owner: string; slug: string }>();

  if (!owner || !slug) {
    return (
      <div className='flex h-full items-center justify-center'>
        <p className='text-muted-foreground'>Invalid agent endpoint URL</p>
      </div>
    );
  }

  return <AgentView owner={owner} slug={slug} />;
}
