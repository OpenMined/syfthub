import { useState } from 'react';

import type { Collective, CollectiveMember } from '@/lib/collectives-api';

import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import Check from 'lucide-react/dist/esm/icons/check';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import X from 'lucide-react/dist/esm/icons/x';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { CollectiveIcon } from '@/components/collectives/collective-icon';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useAuth } from '@/context/auth-context';
import {
  useCollectiveBySlug,
  useInvitation,
  useRespondToInvitation
} from '@/hooks/use-collectives';
import { formatDate } from '@/lib/date-utils';

/**
 * Invitation-response landing page (`/collectives/:slug/invitations/:endpointId`).
 *
 * Linked from the invitation email. The recipient (endpoint owner) sees the
 * invitation details and can accept or decline; the page also handles the
 * already-responded states so re-visiting the email link doesn't 409.
 */
export default function CollectiveInvitationPage() {
  const { slug, endpointId } = useParams<{ slug: string; endpointId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const endpointIdNumber = endpointId ? Number(endpointId) : undefined;

  const {
    data: collective,
    isLoading: collectiveLoading,
    isError: collectiveError
  } = useCollectiveBySlug(slug);
  const {
    data: invitation,
    isLoading: invitationLoading,
    error: invitationError
  } = useInvitation(collective?.id, endpointIdNumber);

  if (collectiveLoading || invitationLoading) {
    return (
      <div className='flex min-h-[60vh] items-center justify-center'>
        <LoadingSpinner />
      </div>
    );
  }

  if (collectiveError || !collective) {
    return (
      <ErrorState
        title='Collective not found'
        message="The collective in this invitation link doesn't exist or has been deleted."
      />
    );
  }

  if (invitationError || !invitation) {
    const message =
      invitationError instanceof Error
        ? invitationError.message
        : 'This invitation no longer exists.';
    return <ErrorState title='Invitation unavailable' message={message} slug={collective.slug} />;
  }

  return (
    <InvitationContent
      collective={collective}
      invitation={invitation}
      currentUsername={user?.username ?? null}
      onBack={() => {
        void navigate(`/c/${collective.slug}`);
      }}
    />
  );
}

interface InvitationContentProps {
  readonly collective: Collective;
  readonly invitation: CollectiveMember;
  readonly currentUsername: string | null;
  readonly onBack: () => void;
}

function InvitationContent({
  collective,
  invitation,
  currentUsername,
  onBack
}: InvitationContentProps) {
  const respond = useRespondToInvitation();
  const [pendingDecision, setPendingDecision] = useState<'accept' | 'decline' | null>(null);

  // The collective owner CAN read this page (they invited the endpoint), but
  // only the endpoint owner can accept/decline. Hide the action buttons for
  // anyone else so the page still renders informatively.
  const isEndpointOwner =
    currentUsername != null && invitation.endpoint_owner_username === currentUsername;

  const onDecide = (decision: 'accept' | 'decline') => {
    setPendingDecision(decision);
    respond.mutate({
      collectiveId: invitation.collective_id,
      endpointId: invitation.endpoint_id,
      decision
    });
  };

  return (
    <div className='mx-auto max-w-2xl px-6 py-12'>
      <Button
        variant='ghost'
        size='sm'
        className='text-muted-foreground hover:text-foreground mb-6 -ml-2'
        onClick={onBack}
      >
        <ArrowLeft className='mr-2 h-4 w-4' />
        Back to {collective.name}
      </Button>

      <Card className='p-8'>
        <div className='mb-6 flex items-start gap-4'>
          <CollectiveIcon collective={collective} size='lg' />
          <div className='min-w-0 flex-1'>
            <h1 className='font-rubik text-foreground flex flex-wrap items-center gap-2 text-2xl font-semibold'>
              You're invited to {collective.name}
              {collective.verified && (
                <ShieldCheck className='h-5 w-5 text-green-500' aria-label='Verified collective' />
              )}
            </h1>
            {collective.description && (
              <p className='font-inter text-muted-foreground mt-2 text-sm'>
                {collective.description}
              </p>
            )}
          </div>
        </div>

        <div className='border-border bg-muted/30 mb-6 rounded-md border p-4 text-sm'>
          <p className='text-muted-foreground'>
            Endpoint{' '}
            <span className='text-foreground font-medium'>
              {invitation.endpoint_name ?? `#${invitation.endpoint_id}`}
            </span>
            {invitation.endpoint_owner_username && (
              <>
                {' '}
                · <span>@{invitation.endpoint_owner_username}</span>
              </>
            )}
            {invitation.endpoint_type && (
              <>
                {' '}
                · <Badge variant='secondary'>{invitation.endpoint_type}</Badge>
              </>
            )}
          </p>
          <p className='text-muted-foreground mt-1 text-xs'>
            Invited {formatDate(invitation.requested_at)}
          </p>
        </div>

        <StatusPanel invitation={invitation} isEndpointOwner={isEndpointOwner} />

        {invitation.status === 'invited' && isEndpointOwner && (
          <div className='mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end'>
            <Button
              variant='outline'
              disabled={respond.isPending}
              onClick={() => {
                onDecide('decline');
              }}
            >
              <X className='mr-2 h-4 w-4' />
              {respond.isPending && pendingDecision === 'decline' ? 'Declining...' : 'Decline'}
            </Button>
            <Button
              disabled={respond.isPending}
              onClick={() => {
                onDecide('accept');
              }}
            >
              <Check className='mr-2 h-4 w-4' />
              {respond.isPending && pendingDecision === 'accept'
                ? 'Accepting...'
                : 'Accept invitation'}
            </Button>
          </div>
        )}

        {respond.isError && (
          <p className='text-destructive mt-4 text-sm'>
            {respond.error instanceof Error
              ? respond.error.message
              : 'Failed to record your response. Please try again.'}
          </p>
        )}

        {invitation.status === 'approved' && (
          <div className='mt-6'>
            <Button asChild>
              <Link to={`/c/${collective.slug}`}>View collective</Link>
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}

function StatusPanel({
  invitation,
  isEndpointOwner
}: Readonly<{ invitation: CollectiveMember; isEndpointOwner: boolean }>) {
  switch (invitation.status) {
    case 'invited': {
      return isEndpointOwner ? (
        <p className='text-muted-foreground text-sm'>
          Accepting the invitation makes this endpoint a member of the collective. Members can be
          discovered through the collective and used as shared data sources.
        </p>
      ) : (
        <p className='text-muted-foreground text-sm'>
          This invitation is awaiting a response from{' '}
          <span className='text-foreground font-medium'>
            @{invitation.endpoint_owner_username ?? 'the endpoint owner'}
          </span>
          . Only the endpoint owner can accept or decline it.
        </p>
      );
    }
    case 'approved': {
      return (
        <div className='border-border rounded-md border bg-emerald-500/10 p-4 text-sm text-emerald-700 dark:text-emerald-300'>
          This invitation has already been accepted — the endpoint is a member of the collective.
        </div>
      );
    }
    case 'rejected': {
      return (
        <div className='border-border bg-muted text-muted-foreground rounded-md border p-4 text-sm'>
          This invitation was declined. You can re-issue it from the collective admin page if you
          change your mind.
        </div>
      );
    }
    case 'pending': {
      return (
        <div className='border-border bg-muted text-muted-foreground rounded-md border p-4 text-sm'>
          The endpoint owner already requested to join this collective — the collective owner just
          needs to approve the request from the admin page.
        </div>
      );
    }
    default: {
      return null;
    }
  }
}

function ErrorState({
  title,
  message,
  slug
}: Readonly<{ title: string; message: string; slug?: string }>) {
  return (
    <div className='mx-auto max-w-xl px-6 py-16 text-center'>
      <h1 className='font-rubik text-foreground mb-4 text-2xl font-semibold'>{title}</h1>
      <p className='text-muted-foreground mb-6'>{message}</p>
      <Button asChild>
        <Link to={slug ? `/c/${slug}` : '/browse?tab=collectives'}>
          {slug ? 'Back to collective' : 'Browse collectives'}
        </Link>
      </Button>
    </div>
  );
}
