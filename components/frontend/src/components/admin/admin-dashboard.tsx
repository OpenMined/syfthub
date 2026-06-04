import { useState } from 'react';

import type { TrendDays } from '@/hooks/use-admin-api';

import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';

import { Card } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { useAdminOverview } from '@/hooks/use-admin-api';

import { LastLoginSection } from './last-login-section';
import { OverviewSection } from './overview-section';
import { SignupTrendCard } from './signup-trend-card';
import { UsersTable } from './users-table';

/** Skeleton placeholders shown while the overview metrics load. */
function OverviewSkeleton() {
  return (
    <div className='flex flex-col gap-6' aria-hidden='true'>
      <div className='grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4'>
        {Array.from({ length: 4 }, (_, index) => (
          <Card key={index} className='border-border/50 h-28 animate-pulse' />
        ))}
      </div>
      <div className='grid grid-cols-1 gap-6 lg:grid-cols-2'>
        <Card className='border-border/50 h-64 animate-pulse' />
        <Card className='border-border/50 h-64 animate-pulse' />
      </div>
    </div>
  );
}

/**
 * Admin user-overview dashboard.
 *
 * Composes the overview KPI section, the signup-trend chart (with a 7/30/90-day
 * range toggle), the last-login activity section, and the paginated users
 * table. Overview metrics and the trend window live here; the users table owns
 * its own query state.
 */
export function AdminDashboard() {
  const [range, setRange] = useState<TrendDays>(30);
  const { data, isLoading, isError, error, isFetching } = useAdminOverview(range);

  let overview: React.ReactNode;
  if (isLoading) {
    overview = <OverviewSkeleton />;
  } else if (isError || !data) {
    overview = (
      <Card className='border-border/50 text-destructive flex flex-col items-center gap-2 p-10 text-center'>
        <AlertCircle className='size-8' aria-hidden='true' />
        <p className='text-sm'>
          {error instanceof Error ? error.message : 'Failed to load overview metrics.'}
        </p>
      </Card>
    );
  } else {
    overview = (
      <div className='flex flex-col gap-8'>
        <OverviewSection
          headline={data.headline}
          byRole={data.by_role}
          byAuthProvider={data.by_auth_provider}
        />
        <SignupTrendCard
          trend={data.signup_trend}
          range={range}
          onRangeChange={setRange}
          isFetching={isFetching}
        />
        <LastLoginSection stats={data.last_login} totalUsers={data.headline.total_users} />
      </div>
    );
  }

  return (
    <>
      <PageHeader title='Users' path='~/admin' />
      <div className='mx-auto flex max-w-6xl flex-col gap-10 px-6 py-8'>
        <div className='flex flex-col gap-1'>
          <h1 className='text-foreground text-2xl font-semibold'>User overview</h1>
          <p className='text-muted-foreground text-sm'>
            Registrations, activity, and account health across the platform.
          </p>
        </div>

        {overview}

        <UsersTable />
      </div>
    </>
  );
}
