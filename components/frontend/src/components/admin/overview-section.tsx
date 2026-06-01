import type { AuthProviderCount, HeadlineCounts, RoleCount } from '@/lib/types';

import MailCheck from 'lucide-react/dist/esm/icons/mail-check';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import UserCheck from 'lucide-react/dist/esm/icons/user-check';
import UsersRound from 'lucide-react/dist/esm/icons/users-round';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { percent } from '@/lib/utils';

import { KpiCard } from './kpi-card';

interface OverviewSectionProperties {
  headline: HeadlineCounts;
  byRole: RoleCount[];
  byAuthProvider: AuthProviderCount[];
}

const ROLE_LABEL: Record<string, string> = {
  admin: 'Admins',
  user: 'Users',
  guest: 'Guests'
};

const PROVIDER_LABEL: Record<string, string> = {
  local: 'Email & password',
  google: 'Google'
};

/**
 * Headline KPI grid plus the role and auth-provider breakdown cards. Pure
 * presentation — all numbers are computed server-side and passed in.
 */
export function OverviewSection({
  headline,
  byRole,
  byAuthProvider
}: Readonly<OverviewSectionProperties>) {
  const verifiedPct = percent(headline.email_verified, headline.total_users);
  const activePct = percent(headline.active_users, headline.total_users);

  return (
    <section aria-labelledby='admin-overview-heading' className='flex flex-col gap-4'>
      <h2 id='admin-overview-heading' className='sr-only'>
        User overview
      </h2>

      <div className='grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4'>
        <KpiCard
          label='Total Users'
          value={headline.total_users}
          icon={UsersRound}
          hint='All registered accounts'
        />
        <KpiCard
          label='Active Users'
          value={headline.active_users}
          icon={UserCheck}
          delta={`${activePct}% of total`}
          deltaTone='positive'
          hint={`${headline.inactive_users.toLocaleString()} inactive`}
        />
        <KpiCard
          label='Email Verified'
          value={headline.email_verified}
          icon={MailCheck}
          delta={`${verifiedPct}% verified`}
          deltaTone={verifiedPct >= 50 ? 'positive' : 'negative'}
          hint={`${headline.email_unverified.toLocaleString()} unverified`}
        />
        <KpiCard
          label='Administrators'
          value={headline.admins}
          icon={ShieldCheck}
          hint='Accounts with admin role'
        />
      </div>

      <div className='grid grid-cols-1 gap-6 md:grid-cols-2'>
        <Card className='border-border/50'>
          <CardHeader>
            <CardTitle className='text-base'>Users by role</CardTitle>
          </CardHeader>
          <CardContent className='flex flex-col gap-3'>
            {byRole.length === 0 ? (
              <p className='text-muted-foreground text-sm'>No users yet.</p>
            ) : (
              byRole.map((row) => (
                <div key={row.role} className='flex items-center justify-between'>
                  <Badge variant={row.role === 'admin' ? 'default' : 'secondary'}>
                    {ROLE_LABEL[row.role] ?? row.role}
                  </Badge>
                  <span className='text-foreground text-sm font-medium tabular-nums'>
                    {row.count.toLocaleString()}
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card className='border-border/50'>
          <CardHeader>
            <CardTitle className='text-base'>Sign-in method</CardTitle>
          </CardHeader>
          <CardContent className='flex flex-col gap-3'>
            {byAuthProvider.length === 0 ? (
              <p className='text-muted-foreground text-sm'>No users yet.</p>
            ) : (
              byAuthProvider.map((row) => (
                <div key={row.provider} className='flex items-center justify-between'>
                  <Badge variant='outline'>{PROVIDER_LABEL[row.provider] ?? row.provider}</Badge>
                  <span className='text-foreground text-sm font-medium tabular-nums'>
                    {row.count.toLocaleString()}
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
