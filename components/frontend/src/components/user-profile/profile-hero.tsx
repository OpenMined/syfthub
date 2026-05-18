import { useState } from 'react';

import type { PublicUserProfile } from '@/lib/types';

import Check from 'lucide-react/dist/esm/icons/check';
import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';
import Copy from 'lucide-react/dist/esm/icons/copy';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Mail from 'lucide-react/dist/esm/icons/mail';
import Pencil from 'lucide-react/dist/esm/icons/pencil';
import UserIcon from 'lucide-react/dist/esm/icons/user';
import Users from 'lucide-react/dist/esm/icons/users';
import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatDateLong } from '@/lib/date-utils';
import { getUserCollectivesByUsername } from '@/lib/mock-data/collectives';

interface ProfileHeroProps {
  username: string;
  profile: PublicUserProfile | null;
  isOwnProfile: boolean;
}

function getInitials(name: string, fallback: string): string {
  const source = (name || fallback).trim();
  if (!source) return '?';
  const parts = source.split(/\s+/).filter(Boolean);
  const initials = parts.slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '');
  return initials.join('') || (source[0]?.toUpperCase() ?? '?');
}

function normalizeDomainHref(domain: string): string {
  if (/^https?:\/\//i.test(domain)) return domain;
  return `https://${domain}`;
}

export function ProfileHero({ username, profile, isOwnProfile }: Readonly<ProfileHeroProps>) {
  const [copied, setCopied] = useState(false);

  const trimmedFullName = profile?.full_name.trim() ?? '';
  const displayName = trimmedFullName === '' ? username : trimmedFullName;
  const initials = getInitials(displayName, username);
  const memberSince = profile?.created_at ? formatDateLong(profile.created_at) : null;
  const showEmail = Boolean(profile?.email);
  const showDomain = Boolean(profile?.domain);
  const userCollectives = getUserCollectivesByUsername(username);

  const handleCopyEmail = () => {
    if (!profile?.email) return;
    void navigator.clipboard.writeText(profile.email).then(() => {
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2000);
    });
  };

  return (
    <header className='border-border bg-card border-b'>
      <div className='mx-auto max-w-5xl px-6 py-8'>
        <div className='flex flex-col gap-6 sm:flex-row sm:items-start'>
          {/* Avatar */}
          <div
            className='from-secondary to-chart-3 flex h-24 w-24 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br text-white shadow-sm'
            role='img'
            aria-label={`Avatar for ${displayName}`}
          >
            {profile?.avatar_url ? (
              <img
                src={profile.avatar_url}
                alt={displayName}
                width={96}
                height={96}
                loading='lazy'
                className='h-24 w-24 rounded-full object-cover'
              />
            ) : (
              <span className='font-rubik text-2xl font-medium tracking-wide'>{initials}</span>
            )}
          </div>

          {/* Identity + actions */}
          <div className='min-w-0 flex-1'>
            <div className='flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between'>
              <div className='min-w-0'>
                <h1 className='font-rubik text-foreground truncate text-3xl font-medium'>
                  {displayName}
                </h1>
                <div className='mt-1 flex items-center gap-2'>
                  <p className='text-muted-foreground truncate font-mono text-sm'>@{username}</p>
                  {profile?.role && profile.role !== 'user' ? (
                    <Badge
                      variant='outline'
                      className='font-inter text-[10px] tracking-wider uppercase'
                    >
                      {profile.role}
                    </Badge>
                  ) : null}
                </div>
              </div>

              {isOwnProfile ? (
                <div className='flex flex-shrink-0 items-center gap-2'>
                  <Button asChild variant='outline' size='sm' className='gap-2'>
                    <Link to='/profile'>
                      <Pencil className='h-3.5 w-3.5' aria-hidden='true' />
                      Edit profile
                    </Link>
                  </Button>
                </div>
              ) : null}
            </div>

            {/* Contact row */}
            {(showEmail || showDomain || memberSince) && (
              <div className='mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm'>
                {showEmail ? (
                  <div className='text-muted-foreground flex items-center gap-1.5'>
                    <Mail className='h-3.5 w-3.5' aria-hidden='true' />
                    <a
                      href={`mailto:${profile?.email ?? ''}`}
                      className='font-inter hover:text-foreground transition-colors'
                    >
                      {profile?.email}
                    </a>
                    <button
                      type='button'
                      onClick={handleCopyEmail}
                      className='hover:text-foreground ml-0.5 inline-flex h-5 w-5 items-center justify-center rounded transition-colors'
                      aria-label='Copy email address'
                    >
                      {copied ? (
                        <Check className='h-3 w-3 text-green-500' aria-hidden='true' />
                      ) : (
                        <Copy className='h-3 w-3' aria-hidden='true' />
                      )}
                    </button>
                  </div>
                ) : null}

                {showDomain && profile?.domain ? (
                  <div className='text-muted-foreground flex items-center gap-1.5'>
                    <Globe className='h-3.5 w-3.5' aria-hidden='true' />
                    <a
                      href={normalizeDomainHref(profile.domain)}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='font-inter hover:text-foreground inline-flex items-center gap-0.5 transition-colors'
                    >
                      {profile.domain.replace(/^https?:\/\//, '')}
                      <ExternalLink className='h-3 w-3' aria-hidden='true' />
                    </a>
                  </div>
                ) : null}

                {memberSince ? (
                  <div className='text-muted-foreground flex items-center gap-1.5'>
                    <UserIcon className='h-3.5 w-3.5' aria-hidden='true' />
                    <span className='font-inter'>Joined {memberSince}</span>
                  </div>
                ) : null}
              </div>
            )}

            {/* Collective badges */}
            {userCollectives.length > 0 && (
              <div className='mt-4 flex flex-wrap items-center gap-2'>
                <div className='flex items-center gap-1.5 text-muted-foreground'>
                  <Users className='h-3.5 w-3.5' />
                  <span className='text-sm'>Member of:</span>
                </div>
                {userCollectives.map((membership) => (
                  <Link
                    key={membership.collective.id}
                    to={`/c/${membership.collective.slug}`}
                    className='inline-flex'
                  >
                    <Badge 
                      variant='secondary' 
                      className='hover:bg-primary/10 transition-colors cursor-pointer'
                    >
                      {membership.collective.name}
                      {membership.collective.verified && (
                        <CheckCircle className='ml-1 h-3 w-3 text-green-500' />
                      )}
                      {membership.role !== 'member' && (
                        <span className='ml-1.5 text-xs opacity-60'>({membership.role})</span>
                      )}
                    </Badge>
                  </Link>
                ))}
              </div>
            )}

            {isOwnProfile ? (
              <p className='font-inter text-muted-foreground mt-4 text-xs'>
                This is how others see your public profile.
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </header>
  );
}
