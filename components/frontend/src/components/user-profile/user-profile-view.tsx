import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/auth-context';
import { useEndpointsByOwner } from '@/hooks/use-endpoint-queries';
import { useUserProfile } from '@/hooks/use-user-profile';

import { ProfileAbout } from './profile-about';
import { ProfileEndpointsList } from './profile-endpoints-list';
import { ProfileHero } from './profile-hero';
import { ProfileSkeleton } from './profile-skeleton';
import { ProfileStatsStrip } from './profile-stats-strip';

interface UserProfileViewProps {
  username: string;
}

export function UserProfileView({ username }: Readonly<UserProfileViewProps>) {
  const normalizedUsername = username.toLowerCase();
  const { user } = useAuth();
  const isOwnProfile = user?.username.toLowerCase() === normalizedUsername;

  const profileQuery = useUserProfile(normalizedUsername);
  const endpointsQuery = useEndpointsByOwner(normalizedUsername);

  const isLoading = profileQuery.isLoading || endpointsQuery.isLoading;
  if (isLoading) {
    return <ProfileSkeleton />;
  }

  const profile = profileQuery.data ?? null;
  const endpoints = endpointsQuery.data ?? [];

  // 404: profile fetch returned null AND user has no public endpoints to anchor
  // identity. Profile-fetch errors (network/5xx) also land here so the user
  // sees something actionable rather than a blank page.
  if (!profile && endpoints.length === 0) {
    const isError = profileQuery.isError;
    return (
      <div className='bg-background flex min-h-screen flex-col items-center justify-center px-6 py-16 text-center'>
        <h1 className='font-rubik text-foreground mb-2 text-2xl font-medium'>
          {isError ? 'Profile unavailable' : 'User not found'}
        </h1>
        <p className='font-inter text-muted-foreground mb-6 max-w-md text-sm'>
          {isError ? (
            <>
              We hit an error loading the profile for{' '}
              <span className='font-mono'>@{normalizedUsername}</span>. Please try again in a
              moment.
            </>
          ) : (
            <>
              We couldn&rsquo;t find a public profile for{' '}
              <span className='font-mono'>@{normalizedUsername}</span>. The account may be
              deactivated or the URL may contain a typo.
            </>
          )}
        </p>
        <div className='flex gap-3'>
          <Button asChild variant='outline'>
            <Link to='/browse'>Browse endpoints</Link>
          </Button>
          <Button asChild>
            <Link to='/'>Go home</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className='bg-background min-h-screen pb-24'>
      <ProfileHero username={normalizedUsername} profile={profile} isOwnProfile={isOwnProfile} />
      <ProfileStatsStrip endpoints={endpoints} />

      <main className='mx-auto max-w-5xl px-6 py-8'>
        {profile?.bio ? <ProfileAbout bio={profile.bio} /> : null}
        <ProfileEndpointsList
          username={normalizedUsername}
          endpoints={endpoints}
          isOwnProfile={isOwnProfile}
        />
      </main>
    </div>
  );
}
