import { useParams } from 'react-router-dom';

import { UserProfileView } from '@/components/user-profile/user-profile-view';

/**
 * Public user profile page rendered at ``/:username`` (e.g. ``/cambridge-press-oa``).
 *
 * Coexists with the GitHub-style ``/:username/:slug`` endpoint detail route —
 * the segment count differs so the routes never collide. Reserved top-level
 * paths (``browse``, ``chat``, ``profile``, etc.) are registered explicitly in
 * ``app.tsx`` and win on react-router specificity.
 */
export default function UserProfilePage() {
  const { username } = useParams<{ username: string }>();

  if (!username) {
    return (
      <div className='flex min-h-[400px] items-center justify-center'>
        <p className='text-muted-foreground'>Invalid profile URL</p>
      </div>
    );
  }

  return <UserProfileView username={username} />;
}
