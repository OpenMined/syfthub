import { useState } from 'react';

import type { ReactNode } from 'react';

import { useQuery } from '@tanstack/react-query';
import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';
import Database from 'lucide-react/dist/esm/icons/database';
import Settings from 'lucide-react/dist/esm/icons/settings';
import UserPlus from 'lucide-react/dist/esm/icons/user-plus';
import Users from 'lucide-react/dist/esm/icons/users';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/context/auth-context';
import { useCollectiveBySlug, useCollectiveMembers, useRequestJoin } from '@/hooks/use-collectives';
import { formatDateLong } from '@/lib/date-utils';
import { getUserEndpoints } from '@/lib/endpoint-utils';

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

  if (isLoading) {
    return (
      <div className='flex min-h-[60vh] items-center justify-center'>
        <LoadingSpinner />
      </div>
    );
  }

  if (isError || !collective) {
    return (
      <div className='container mx-auto px-6 py-16 text-center'>
        <h1 className='mb-4 text-2xl font-bold'>Collective not found</h1>
        <p className='text-muted-foreground mb-6'>
          The collective you're looking for doesn't exist.
        </p>
        <Button asChild>
          <Link to='/collectives/browse'>Browse collectives</Link>
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
            onClick={() => navigate('/collectives/browse')}
            className='mb-4 -ml-2'
          >
            <ArrowLeft className='mr-2 h-4 w-4' />
            Back to Collectives
          </Button>

          <div className='mb-4 flex items-start gap-4'>
            {collective.icon_url ? (
              <img
                src={collective.icon_url}
                alt={collective.name}
                className='h-14 w-14 rounded-lg object-cover'
              />
            ) : (
              <div className='from-primary/20 to-primary/10 flex h-14 w-14 items-center justify-center rounded-lg bg-gradient-to-br'>
                <Users className='text-primary h-7 w-7' />
              </div>
            )}
            <div className='min-w-0 flex-1'>
              <div className='mb-1 flex items-center gap-2'>
                <h1 className='text-2xl font-bold'>{collective.name}</h1>
                {collective.verified && (
                  <CheckCircle
                    className='h-5 w-5 text-green-500'
                    aria-label='Verified collective'
                  />
                )}
              </div>
              <p className='text-muted-foreground'>
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
            <Badge variant='outline'>
              {collective.auto_approve ? 'Open — auto-approves' : 'Request to join'}
            </Badge>
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

      {/* Content */}
      <div className='mx-auto max-w-5xl px-6 py-8'>
        <div className='grid gap-8 lg:grid-cols-3'>
          {/* Members */}
          <div className='lg:col-span-2'>
            <Card className='border-border bg-card rounded-xl border p-6'>
              <h2 className='mb-4 flex items-center gap-2 text-lg font-semibold'>
                <Database className='h-5 w-5' />
                Endpoints
                <span className='text-muted-foreground text-sm font-normal'>
                  ({approvedMembers.length})
                </span>
              </h2>

              {approvedMembers.length > 0 ? (
                <div className='space-y-3'>
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
                            {member.endpoint_owner_username && (
                              <p className='text-muted-foreground mt-0.5 text-xs'>
                                by @{member.endpoint_owner_username}
                              </p>
                            )}
                          </div>
                          {member.endpoint_type && (
                            <Badge variant='outline' className='shrink-0 text-xs'>
                              {member.endpoint_type === 'model' ? 'model' : 'data'}
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
            </Card>
          </div>

          {/* Sidebar */}
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

            <Card className='border-border bg-card rounded-xl border p-6'>
              <div className='space-y-4'>
                <div>
                  <div className='text-muted-foreground mb-1 flex items-center gap-2 text-sm'>
                    <Database className='h-4 w-4' />
                    Endpoints
                  </div>
                  <div className='text-2xl font-semibold'>{collective.member_count}</div>
                </div>
                <div className='border-t pt-4 text-sm'>
                  <span className='text-muted-foreground'>Created </span>
                  {formatDateLong(collective.created_at)}
                </div>
              </div>
            </Card>
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
  const [selectedEndpointId, setSelectedEndpointId] = useState<number | null>(null);
  const requestJoin = useRequestJoin();

  const { data: endpoints, isLoading } = useQuery({
    queryKey: ['my-endpoints', username],
    queryFn: () => getUserEndpoints({}, username),
    enabled: isOpen
  });

  const handleClose = () => {
    setSelectedEndpointId(null);
    requestJoin.reset();
    onClose();
  };

  const handleSubmit = () => {
    if (selectedEndpointId == null) return;
    requestJoin.mutate(
      { collectiveId, endpointId: selectedEndpointId },
      { onSuccess: handleClose }
    );
  };

  let endpointPicker: ReactNode;
  if (isLoading) {
    endpointPicker = (
      <div className='flex justify-center py-6'>
        <LoadingSpinner />
      </div>
    );
  } else if (endpoints && endpoints.length > 0) {
    endpointPicker = (
      <div className='max-h-64 space-y-2 overflow-y-auto'>
        {endpoints.map((endpoint) => (
          <button
            key={endpoint.id}
            type='button'
            onClick={() => {
              setSelectedEndpointId(endpoint.id);
            }}
            className={`w-full rounded-lg border p-3 text-left transition-colors ${
              selectedEndpointId === endpoint.id
                ? 'border-primary bg-primary/5'
                : 'border-border hover:bg-muted/50'
            }`}
          >
            <p className='text-sm font-medium'>{endpoint.name}</p>
            <p className='text-muted-foreground text-xs'>
              @{username}/{endpoint.slug}
            </p>
          </button>
        ))}
      </div>
    );
  } else {
    endpointPicker = (
      <p className='text-muted-foreground py-4 text-center text-sm'>
        You have no endpoints to submit yet.
      </p>
    );
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={`Join ${collectiveName}`}>
      <div className='space-y-4'>
        <p className='text-muted-foreground text-sm'>
          Choose one of your endpoints to submit to this collective.
        </p>

        {endpointPicker}

        {requestJoin.isError && (
          <p className='text-destructive text-sm'>
            {requestJoin.error instanceof Error
              ? requestJoin.error.message
              : 'Failed to submit request'}
          </p>
        )}

        <div className='flex justify-end gap-2'>
          <Button variant='outline' onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={selectedEndpointId == null || requestJoin.isPending}
          >
            {requestJoin.isPending ? 'Submitting...' : 'Submit'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
