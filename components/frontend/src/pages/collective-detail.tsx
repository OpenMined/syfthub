import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { EndpointType } from '@/lib/types';
import type { ReactNode } from 'react';

import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import Check from 'lucide-react/dist/esm/icons/check';
import Copy from 'lucide-react/dist/esm/icons/copy';
import Database from 'lucide-react/dist/esm/icons/database';
import Settings from 'lucide-react/dist/esm/icons/settings';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import UserPlus from 'lucide-react/dist/esm/icons/user-plus';
import Users from 'lucide-react/dist/esm/icons/users';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { CollectiveAbout } from '@/components/collectives/collective-about';
import { CollectiveIcon } from '@/components/collectives/collective-icon';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/context/auth-context';
import {
  useCollectiveBySlug,
  useCollectiveMembers,
  useRequestJoinMany
} from '@/hooks/use-collectives';
import { useMyEndpoints } from '@/hooks/use-endpoint-queries';
import { isJoinableEndpointType } from '@/lib/collectives-api';
import { getEndpointTypeLabel } from '@/lib/endpoint-utils';

/** Up-to-two-letter initials from a display name. */
function getInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  return words
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('');
}

// Stable accent palette for owner avatars — picked by hashing the username.
const AVATAR_COLORS = [
  'bg-indigo-500/15 text-indigo-600',
  'bg-emerald-500/15 text-emerald-600',
  'bg-rose-500/15 text-rose-600',
  'bg-amber-500/15 text-amber-600',
  'bg-sky-500/15 text-sky-600',
  'bg-violet-500/15 text-violet-600'
];

function avatarColor(seed: string): string {
  let hash = 0;
  for (const char of seed) {
    hash = (hash * 31 + (char.codePointAt(0) ?? 0)) % 1_000_000_007;
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length] ?? AVATAR_COLORS[0] ?? 'bg-muted';
}

/**
 * Public collective detail page (`/c/:slug`).
 *
 * Shows the collective and its approved endpoint members. Endpoint owners can
 * request that one of their endpoints join.
 */
export default function CollectiveDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const { data: collective, isLoading, isError } = useCollectiveBySlug(slug);
  const { data: members } = useCollectiveMembers(collective?.id, 'approved');

  const [showJoinModal, setShowJoinModal] = useState(false);
  const [cardTab, setCardTab] = useState<'endpoints' | 'members'>('endpoints');

  // The collective's "members" are the distinct owners of its endpoints —
  // derived from each approved membership's endpoint_owner_username.
  const owners = useMemo(() => {
    const map = new Map<string, { fullName: string; endpointCount: number }>();
    for (const membership of members ?? []) {
      const username = membership.endpoint_owner_username;
      if (!username) continue;
      const existing = map.get(username);
      if (existing) {
        existing.endpointCount += 1;
      } else {
        const fullName = membership.endpoint_owner_full_name?.trim() ?? '';
        map.set(username, {
          fullName: fullName.length > 0 ? fullName : username,
          endpointCount: 1
        });
      }
    }
    return [...map.entries()]
      .map(([username, info]) => ({ username, ...info }))
      .toSorted(
        (a, b) => b.endpointCount - a.endpointCount || a.username.localeCompare(b.username)
      );
  }, [members]);

  if (isLoading) {
    return (
      <div className='flex min-h-[60vh] items-center justify-center'>
        <LoadingSpinner />
      </div>
    );
  }

  if (isError || !collective) {
    return (
      <div className='mx-auto max-w-2xl px-6 py-16 text-center'>
        <h1 className='font-rubik text-foreground mb-4 text-2xl font-semibold'>
          Collective not found
        </h1>
        <p className='font-inter text-muted-foreground mb-6'>
          The collective you're looking for doesn't exist.
        </p>
        <Button asChild>
          <Link to='/browse?tab=collectives'>Browse collectives</Link>
        </Button>
      </div>
    );
  }

  const isOwner = user != null && Number(user.id) === collective.owner_id;
  const approvedMembers = members ?? [];

  return (
    <div className='bg-background min-h-screen'>
      {/* Header */}
      <div className='border-border bg-card sticky top-0 z-10 border-b backdrop-blur-sm'>
        <div className='mx-auto max-w-5xl px-6 py-4'>
          <Button
            variant='ghost'
            size='sm'
            onClick={() => navigate('/browse?tab=collectives')}
            className='text-muted-foreground hover:text-foreground mb-4 -ml-2'
          >
            <ArrowLeft className='mr-2 h-4 w-4' />
            Back to Collectives
          </Button>

          <div className='mb-4 flex items-start gap-4'>
            <CollectiveIcon collective={collective} size='lg' />
            <div className='min-w-0 flex-1'>
              <div className='mb-1 flex items-center gap-2'>
                <h1 className='font-rubik text-foreground text-3xl font-medium'>
                  {collective.name}
                </h1>
                {collective.verified && (
                  <ShieldCheck
                    className='h-5 w-5 text-green-500'
                    aria-label='Verified collective'
                  />
                )}
              </div>
              <p className='font-inter text-muted-foreground text-lg'>
                {collective.description || 'No description provided.'}
              </p>
            </div>
          </div>

          <div className='flex flex-wrap items-center gap-2'>
            {collective.tags.map((tag) => (
              <Badge key={tag} variant='secondary'>
                {tag}
              </Badge>
            ))}
            {isOwner && (
              <Button asChild variant='outline' size='sm' className='ml-auto'>
                <Link to={`/c/${collective.slug}/admin`}>
                  <Settings className='mr-2 h-4 w-4' />
                  Manage
                </Link>
              </Button>
            )}
          </div>
        </div>
      </div>

      <div className='mx-auto max-w-5xl px-6 py-8'>
        <div className='grid gap-8 lg:grid-cols-3'>
          {/* Main column */}
          <div className='space-y-6 lg:col-span-2'>
            {collective.about.trim() && <CollectiveAbout about={collective.about} />}

            {/* Endpoints & Members */}
            <Card className='p-6'>
              <div className='mb-4 flex gap-4 border-b'>
                {(['endpoints', 'members'] as const).map((tab) => (
                  <button
                    key={tab}
                    type='button'
                    onClick={() => {
                      setCardTab(tab);
                    }}
                    className={`-mb-[2px] flex items-center gap-1.5 border-b-2 px-1 py-2 text-sm font-medium capitalize transition-colors ${
                      cardTab === tab
                        ? 'border-primary text-foreground'
                        : 'text-muted-foreground hover:text-foreground border-transparent'
                    }`}
                  >
                    {tab === 'endpoints' ? (
                      <Database className='h-4 w-4' />
                    ) : (
                      <Users className='h-4 w-4' />
                    )}
                    {tab}
                    <span className='text-muted-foreground text-xs font-normal'>
                      ({tab === 'endpoints' ? approvedMembers.length : owners.length})
                    </span>
                  </button>
                ))}
              </div>

              {/* Endpoints tab */}
              {cardTab === 'endpoints' && (
                <div>
                  {approvedMembers.length > 0 ? (
                    // Caps the list at ~3 endpoint rows; scrolls when there are more.
                    <div className='max-h-[22rem] space-y-3 overflow-y-auto pr-1'>
                      {approvedMembers.map((member) => {
                        const href =
                          member.endpoint_owner_username && member.endpoint_slug
                            ? `/${member.endpoint_owner_username}/${member.endpoint_slug}`
                            : null;
                        const row = (
                          <Card className='hover:border-primary/30 p-3 transition-all'>
                            <div className='flex items-start justify-between gap-3'>
                              <div className='min-w-0'>
                                <h4 className='hover:text-primary truncate text-sm font-medium transition-colors'>
                                  {member.endpoint_name ?? `Endpoint #${member.endpoint_id}`}
                                </h4>
                                {member.endpoint_description && (
                                  <p className='text-muted-foreground mt-1 line-clamp-2 text-xs'>
                                    {member.endpoint_description}
                                  </p>
                                )}
                                {member.endpoint_owner_username && (
                                  <p className='text-muted-foreground mt-1 text-xs'>
                                    by @{member.endpoint_owner_username}
                                  </p>
                                )}
                              </div>
                              {member.endpoint_type && (
                                <Badge variant='outline' className='shrink-0 text-xs'>
                                  {getEndpointTypeLabel(member.endpoint_type as EndpointType)}
                                </Badge>
                              )}
                            </div>
                          </Card>
                        );
                        return href ? (
                          <Link key={member.id} to={href} className='block'>
                            {row}
                          </Link>
                        ) : (
                          <div key={member.id}>{row}</div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className='text-muted-foreground py-8 text-center text-sm'>
                      No endpoints have joined this collective yet.
                    </p>
                  )}
                </div>
              )}

              {/* Members tab — distinct owners of the collective's endpoints */}
              {cardTab === 'members' && (
                <div>
                  {owners.length > 0 ? (
                    // Same capped, scrollable list height as the Endpoints tab.
                    <div className='max-h-[22rem] space-y-3 overflow-y-auto pr-1'>
                      {owners.map((owner) => (
                        <Link key={owner.username} to={`/${owner.username}`} className='block'>
                          <Card className='hover:border-primary/30 p-3 transition-all'>
                            <div className='flex items-center justify-between gap-3'>
                              <div className='flex min-w-0 items-center gap-3'>
                                <Avatar className='h-9 w-9 shrink-0'>
                                  <AvatarFallback
                                    className={`font-medium ${avatarColor(owner.username)}`}
                                  >
                                    {getInitials(owner.fullName)}
                                  </AvatarFallback>
                                </Avatar>
                                <div className='min-w-0'>
                                  <p className='hover:text-primary truncate text-sm font-medium transition-colors'>
                                    {owner.fullName}
                                  </p>
                                  <p className='text-muted-foreground truncate text-xs'>
                                    @{owner.username}
                                  </p>
                                </div>
                              </div>
                              <span className='text-muted-foreground shrink-0 text-xs'>
                                {owner.endpointCount}{' '}
                                {owner.endpointCount === 1 ? 'endpoint' : 'endpoints'}
                              </span>
                            </div>
                          </Card>
                        </Link>
                      ))}
                    </div>
                  ) : (
                    <p className='text-muted-foreground py-8 text-center text-sm'>
                      No members yet.
                    </p>
                  )}
                </div>
              )}
            </Card>
          </div>

          <div className='space-y-6'>
            {!isOwner && user != null && (
              <Button
                className='w-full'
                onClick={() => {
                  setShowJoinModal(true);
                }}
              >
                <UserPlus className='mr-2 h-4 w-4' />
                {collective.auto_approve ? 'Join Collective' : 'Request to Join'}
              </Button>
            )}

            <Card className='p-6'>
              <div className='space-y-4'>
                <div>
                  <div className='text-muted-foreground mb-1 flex items-center gap-2 text-sm'>
                    <Users className='h-4 w-4' />
                    Members
                  </div>
                  <div className='text-2xl font-semibold'>{collective.owner_count}</div>
                </div>
                <div>
                  <div className='text-muted-foreground mb-1 flex items-center gap-2 text-sm'>
                    <Database className='h-4 w-4' />
                    Endpoints
                  </div>
                  <div className='text-2xl font-semibold'>{collective.member_count}</div>
                </div>
              </div>
            </Card>

            <SharedEndpointCard
              path={collective.shared_endpoint_path}
              endpointCount={collective.member_count}
            />
          </div>
        </div>
      </div>

      {user != null && (
        <JoinCollectiveModal
          isOpen={showJoinModal}
          onClose={() => {
            setShowJoinModal(false);
          }}
          collectiveId={collective.id}
          collectiveName={collective.name}
          username={user.username}
        />
      )}
    </div>
  );
}

/**
 * Sidebar card showing the collective's unique shared-endpoint path
 * (`collective/<slug>`) — the single identifier that addresses every member
 * endpoint at once.
 */
function SharedEndpointCard({
  path,
  endpointCount
}: Readonly<{ path: string; endpointCount: number }>) {
  const [copied, setCopied] = useState(false);
  const timerReference = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timerReference.current) clearTimeout(timerReference.current);
    },
    []
  );

  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(path);
    setCopied(true);
    if (timerReference.current) clearTimeout(timerReference.current);
    timerReference.current = setTimeout(() => {
      setCopied(false);
    }, 2000);
  }, [path]);

  return (
    <Card className='p-6'>
      <h3 className='mb-1 text-sm leading-none font-semibold'>Shared Endpoint</h3>
      <p className='text-muted-foreground mb-1.5 text-xs leading-none'>
        Query all {endpointCount} {endpointCount === 1 ? 'endpoint' : 'endpoints'} through a single
        API
      </p>
      <div className='border-border bg-muted/50 flex items-center gap-2 rounded-lg border px-3 py-2'>
        <code className='text-muted-foreground min-w-0 flex-1 truncate font-mono text-xs'>
          {path}
        </code>
        <button
          type='button'
          onClick={handleCopy}
          aria-label={copied ? 'Shared endpoint path copied' : 'Copy shared endpoint path'}
          className='text-muted-foreground hover:text-foreground shrink-0 transition-colors'
        >
          {copied ? (
            <Check className='h-3.5 w-3.5 text-green-600' aria-hidden='true' />
          ) : (
            <Copy className='h-3.5 w-3.5' aria-hidden='true' />
          )}
        </button>
      </div>
    </Card>
  );
}

interface JoinModalProps {
  isOpen: boolean;
  onClose: () => void;
  collectiveId: number;
  collectiveName: string;
  username: string;
}

/**
 * Join flow: a collective groups endpoints, so joining means picking one of
 * your endpoints to submit. The backend either approves it immediately
 * (`auto_approve`) or queues it for the collective owner's review.
 */
function JoinCollectiveModal({
  isOpen,
  onClose,
  collectiveId,
  collectiveName,
  username
}: Readonly<JoinModalProps>) {
  const [selectedEndpointIds, setSelectedEndpointIds] = useState<ReadonlySet<number>>(
    () => new Set()
  );
  const requestJoinMany = useRequestJoinMany();

  const { data: endpoints, isLoading } = useMyEndpoints(username, isOpen);

  // Collectives group data sources — only data-source-capable endpoints may
  // join, so model-only and agent endpoints are not offered for selection.
  const joinableEndpoints = useMemo(
    () => (endpoints ?? []).filter((endpoint) => isJoinableEndpointType(endpoint.type)),
    [endpoints]
  );

  const allSelected =
    joinableEndpoints.length > 0 && selectedEndpointIds.size === joinableEndpoints.length;
  const someSelected = selectedEndpointIds.size > 0 && !allSelected;
  let selectAllChecked: boolean | 'indeterminate' = false;
  if (allSelected) {
    selectAllChecked = true;
  } else if (someSelected) {
    selectAllChecked = 'indeterminate';
  }

  const toggleEndpoint = (endpointId: number) => {
    setSelectedEndpointIds((current) => {
      const next = new Set(current);
      if (next.has(endpointId)) {
        next.delete(endpointId);
      } else {
        next.add(endpointId);
      }
      return next;
    });
  };

  const toggleAll = () => {
    setSelectedEndpointIds((current) =>
      current.size === joinableEndpoints.length
        ? new Set()
        : new Set(joinableEndpoints.map((endpoint) => endpoint.id))
    );
  };

  const handleClose = () => {
    setSelectedEndpointIds(new Set());
    requestJoinMany.reset();
    onClose();
  };

  const handleSubmit = () => {
    if (selectedEndpointIds.size === 0) return;
    requestJoinMany.mutate(
      { collectiveId, endpointIds: [...selectedEndpointIds] },
      {
        onSuccess: (result) => {
          // Only close when every request succeeded — otherwise stay open so
          // the user can see which endpoints failed and retry just those.
          if (result.failed.length === 0) {
            handleClose();
          } else {
            setSelectedEndpointIds(new Set(result.failed.map((failure) => failure.endpointId)));
          }
        }
      }
    );
  };

  const failureById = useMemo(() => {
    const map = new Map<number, string>();
    for (const { endpointId, error } of requestJoinMany.data?.failed ?? []) {
      map.set(endpointId, error.message);
    }
    return map;
  }, [requestJoinMany.data]);

  let endpointPicker: ReactNode;
  if (isLoading) {
    endpointPicker = (
      <div className='flex justify-center py-6'>
        <LoadingSpinner />
      </div>
    );
  } else if (joinableEndpoints.length > 0) {
    endpointPicker = (
      <div className='space-y-2'>
        <label className='hover:bg-muted/50 flex cursor-pointer items-center gap-3 rounded-lg border border-dashed px-3 py-2'>
          <Checkbox
            checked={selectAllChecked}
            onCheckedChange={toggleAll}
            aria-label='Select all data source endpoints'
          />
          <span className='text-sm font-medium'>Select all</span>
          <span className='text-muted-foreground ml-auto text-xs'>
            {selectedEndpointIds.size} of {joinableEndpoints.length} selected
          </span>
        </label>
        <div className='max-h-64 space-y-2 overflow-y-auto'>
          {joinableEndpoints.map((endpoint) => {
            const checked = selectedEndpointIds.has(endpoint.id);
            const failureMessage = failureById.get(endpoint.id);
            return (
              <label
                key={endpoint.id}
                className={`flex w-full cursor-pointer items-start gap-3 rounded-lg border p-3 text-left transition-colors ${
                  checked ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/50'
                }`}
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => {
                    toggleEndpoint(endpoint.id);
                  }}
                  className='mt-0.5'
                  aria-label={`Submit ${endpoint.name}`}
                />
                <div className='min-w-0 flex-1'>
                  <p className='text-sm font-medium'>{endpoint.name}</p>
                  <p className='text-muted-foreground truncate text-xs'>
                    @{username}/{endpoint.slug}
                  </p>
                  {failureMessage && (
                    <p className='text-destructive mt-1 text-xs'>{failureMessage}</p>
                  )}
                </div>
              </label>
            );
          })}
        </div>
      </div>
    );
  } else {
    endpointPicker = (
      <p className='text-muted-foreground py-4 text-center text-sm'>
        You have no data source endpoints to submit. Collectives only accept data source endpoints.
      </p>
    );
  }

  const submitLabel = (() => {
    if (requestJoinMany.isPending) return 'Submitting...';
    const count = selectedEndpointIds.size;
    if (count <= 1) return 'Submit';
    return `Submit ${count} endpoints`;
  })();

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={`Join ${collectiveName}`}>
      <div className='space-y-4'>
        <p className='text-muted-foreground text-sm'>
          Choose one or more of your data source endpoints to submit to this collective. Model and
          agent endpoints aren't eligible to join.
        </p>

        {endpointPicker}

        {requestJoinMany.isError && (
          <p className='text-destructive text-sm'>
            {requestJoinMany.error instanceof Error
              ? requestJoinMany.error.message
              : 'Failed to submit request'}
          </p>
        )}
        {requestJoinMany.data && requestJoinMany.data.failed.length > 0 && (
          <p className='text-destructive text-sm'>
            {requestJoinMany.data.succeeded.length > 0
              ? `Submitted ${requestJoinMany.data.succeeded.length} endpoint${
                  requestJoinMany.data.succeeded.length === 1 ? '' : 's'
                }, but ${requestJoinMany.data.failed.length} failed.`
              : `Failed to submit ${requestJoinMany.data.failed.length} endpoint${
                  requestJoinMany.data.failed.length === 1 ? '' : 's'
                }.`}
          </p>
        )}

        <div className='flex justify-end gap-2'>
          <Button variant='outline' onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={selectedEndpointIds.size === 0 || requestJoinMany.isPending}
          >
            {submitLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
