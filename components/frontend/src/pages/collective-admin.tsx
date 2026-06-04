import { useEffect, useMemo, useState } from 'react';

import type { InviteEndpointOption } from '@/components/collectives/invite-combobox';
import type { InviteEndpointsByPathResult } from '@/hooks/use-collectives';
import type { Collective, CollectiveMember } from '@/lib/collectives-api';
import type { ReactNode } from 'react';

import ArrowDownLeft from 'lucide-react/dist/esm/icons/arrow-down-left';
import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import ArrowUpRight from 'lucide-react/dist/esm/icons/arrow-up-right';
import Check from 'lucide-react/dist/esm/icons/check';
import Clock from 'lucide-react/dist/esm/icons/clock';
import Inbox from 'lucide-react/dist/esm/icons/inbox';
import Mail from 'lucide-react/dist/esm/icons/mail';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';
import UserCheck from 'lucide-react/dist/esm/icons/user-check';
import UserPlus from 'lucide-react/dist/esm/icons/user-plus';
import Users from 'lucide-react/dist/esm/icons/users';
import X from 'lucide-react/dist/esm/icons/x';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { InviteCombobox } from '@/components/collectives/invite-combobox';
import { SharedEndpointsTab } from '@/components/collectives/shared-endpoints-tab';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Modal } from '@/components/ui/modal';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useAuth } from '@/context/auth-context';
import {
  useCollectiveBySlug,
  useCollectiveMembers,
  useDeleteCollective,
  useInviteEndpointsByPath,
  useRemoveMember,
  useReviewRequest,
  useUpdateCollective
} from '@/hooks/use-collectives';
import { parseTags } from '@/lib/collectives-api';
import { formatRelativeTime } from '@/lib/date-utils';

type AdminTab = 'members' | 'pending' | 'shared' | 'settings';

/**
 * Collective administration (`/c/:slug/admin`). Owner only — the route is
 * auth-protected and this page additionally checks collective ownership.
 */
export default function CollectiveAdminPage() {
  const { slug } = useParams<{ slug: string }>();
  const { user } = useAuth();
  const { data: collective, isLoading, isError } = useCollectiveBySlug(slug);

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
        <Button asChild>
          <Link to='/browse?tab=collectives'>Browse collectives</Link>
        </Button>
      </div>
    );
  }

  const isOwner = user != null && Number(user.id) === collective.owner_id;
  if (!isOwner) {
    return (
      <div className='mx-auto max-w-2xl px-6 py-16 text-center'>
        <h1 className='font-rubik text-foreground mb-4 text-2xl font-semibold'>Access denied</h1>
        <p className='text-muted-foreground mb-6'>
          You don't have permission to manage this collective.
        </p>
        <Button asChild>
          <Link to={`/c/${collective.slug}`}>Go to collective page</Link>
        </Button>
      </div>
    );
  }

  return <CollectiveAdminContent collective={collective} />;
}

function CollectiveAdminContent({ collective }: Readonly<{ collective: Collective }>) {
  const [activeTab, setActiveTab] = useState<AdminTab>('members');
  const [inviteModalOpen, setInviteModalOpen] = useState(false);

  const { data: approvedMembers } = useCollectiveMembers(collective.id, 'approved');
  const { data: pendingMembers } = useCollectiveMembers(collective.id, 'pending');
  const { data: invitedMembers } = useCollectiveMembers(collective.id, 'invited');
  const removeMember = useRemoveMember();
  const reviewRequest = useReviewRequest();

  const members = approvedMembers ?? [];
  const requests = pendingMembers ?? [];
  const invitations = invitedMembers ?? [];

  const tabs: { id: AdminTab; label: string; badge?: number }[] = [
    { id: 'members', label: 'Members' },
    // One unified "Pending" tab covers both inbound join requests and outbound
    // invitations. The badge counts ONLY requests — the items awaiting *your*
    // review — because invitations are waiting on the other party, not you.
    { id: 'pending', label: 'Pending', badge: requests.length },
    { id: 'shared', label: 'Shared Endpoints' },
    { id: 'settings', label: 'Settings' }
  ];

  return (
    <div className='mx-auto max-w-5xl px-6 py-8'>
      <div className='mb-8'>
        <Button
          asChild
          variant='ghost'
          size='sm'
          className='text-muted-foreground hover:text-foreground mb-4 -ml-2'
        >
          <Link to={`/c/${collective.slug}`}>
            <ArrowLeft className='mr-2 h-4 w-4' />
            Back to {collective.name}
          </Link>
        </Button>
        <div className='flex items-start justify-between gap-4'>
          <div>
            <h1 className='font-rubik text-foreground flex items-center gap-2 text-3xl font-semibold'>
              Manage {collective.name}
              {collective.verified && (
                <ShieldCheck className='h-6 w-6 text-green-500' aria-label='Verified collective' />
              )}
            </h1>
            <p className='font-inter text-muted-foreground mt-1'>
              Administer this collective's members, join requests and settings
            </p>
          </div>
          <Button
            onClick={() => {
              setInviteModalOpen(true);
            }}
            className='shrink-0'
          >
            <UserPlus className='mr-2 h-4 w-4' />
            Invite endpoint
          </Button>
        </div>
      </div>

      <div className='mb-8 grid grid-cols-2 gap-4'>
        <Card className='p-4'>
          <div className='flex items-center gap-3'>
            <Users className='h-8 w-8 text-blue-500' />
            <div>
              <p className='text-2xl font-bold'>{collective.member_count}</p>
              <p className='text-muted-foreground text-xs'>Approved endpoints</p>
            </div>
          </div>
        </Card>
        <Card className='p-4'>
          <div className='flex items-center gap-3'>
            <UserCheck className='h-8 w-8 text-yellow-500' />
            <div>
              <p className='text-2xl font-bold'>{requests.length}</p>
              <p className='text-muted-foreground text-xs'>Pending requests</p>
            </div>
          </div>
        </Card>
      </div>

      <div className='mb-6 flex gap-4 border-b'>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => {
              setActiveTab(tab.id);
            }}
            className={`-mb-[2px] border-b-2 px-1 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'border-primary text-foreground'
                : 'text-muted-foreground hover:text-foreground border-transparent'
            }`}
          >
            {tab.label}
            {tab.badge != null && tab.badge > 0 && (
              <Badge
                variant='outline'
                className='border-primary/20 bg-primary/10 text-primary ml-2 text-xs'
              >
                {tab.badge}
              </Badge>
            )}
          </button>
        ))}
      </div>

      {activeTab === 'members' && (
        <div className='space-y-3'>
          {members.length > 0 ? (
            members.map((member) => (
              <MemberRow
                key={member.id}
                member={member}
                subtitle={
                  <>
                    {member.endpoint_owner_username
                      ? `@${member.endpoint_owner_username}`
                      : 'owner unknown'}
                    {member.endpoint_type ? ` · ${member.endpoint_type}` : ''}
                  </>
                }
                actions={
                  <Button
                    size='sm'
                    variant='ghost'
                    disabled={removeMember.isPending}
                    onClick={() => {
                      removeMember.mutate({
                        collectiveId: collective.id,
                        endpointId: member.endpoint_id
                      });
                    }}
                    title='Remove from collective'
                    className='text-muted-foreground hover:text-destructive'
                  >
                    <Trash2 className='h-4 w-4' />
                  </Button>
                }
              />
            ))
          ) : (
            <Card className='text-muted-foreground p-12 text-center text-sm'>
              No approved endpoints yet.
            </Card>
          )}
        </div>
      )}

      {activeTab === 'pending' && (
        <PendingTab
          collectiveId={collective.id}
          requests={requests}
          invitations={invitations}
          reviewRequest={reviewRequest}
          removeMember={removeMember}
          onInvite={() => {
            setInviteModalOpen(true);
          }}
        />
      )}

      {activeTab === 'shared' && (
        <SharedEndpointsTab collective={collective} approvedMembers={members} />
      )}

      {activeTab === 'settings' && <CollectiveSettingsForm collective={collective} />}

      <InviteEndpointModal
        isOpen={inviteModalOpen}
        collective={collective}
        onClose={() => {
          setInviteModalOpen(false);
        }}
        onInvited={() => {
          setInviteModalOpen(false);
          setActiveTab('pending');
        }}
      />
    </div>
  );
}

function MemberRow({
  member,
  subtitle,
  actions
}: Readonly<{
  member: CollectiveMember;
  subtitle: ReactNode;
  actions: ReactNode;
}>) {
  return (
    <Card className='p-4'>
      <div className='flex items-center justify-between gap-3'>
        <div className='min-w-0'>
          <p className='truncate font-medium'>
            {member.endpoint_name ?? `Endpoint #${member.endpoint_id}`}
          </p>
          <p className='text-muted-foreground text-xs'>{subtitle}</p>
        </div>
        {actions}
      </div>
    </Card>
  );
}

/**
 * Unified "Pending" tab — merges what used to be the separate Requests and
 * Invitations tabs into a single view organised by *whose action is needed*:
 *
 * - "Needs your review" (inbound join requests, status `pending`) — the owner
 *   approves or rejects. Pinned first because it's blocking on the owner.
 * - "Awaiting response" (outbound invitations, status `invited`) — waiting on
 *   the invited endpoint's owner; the collective owner can only cancel.
 *
 * Empty sections are omitted; only when BOTH are empty is the all-caught-up
 * state shown.
 */
function PendingTab({
  collectiveId,
  requests,
  invitations,
  reviewRequest,
  removeMember,
  onInvite
}: Readonly<{
  collectiveId: number;
  requests: CollectiveMember[];
  invitations: CollectiveMember[];
  reviewRequest: ReturnType<typeof useReviewRequest>;
  removeMember: ReturnType<typeof useRemoveMember>;
  onInvite: () => void;
}>) {
  if (requests.length === 0 && invitations.length === 0) {
    return (
      <Card className='flex flex-col items-center gap-3 p-12 text-center'>
        <div className='bg-muted text-muted-foreground rounded-xl p-3'>
          <Inbox className='h-6 w-6' />
        </div>
        <div>
          <p className='text-foreground text-sm font-medium'>You're all caught up</p>
          <p className='text-muted-foreground mt-1 text-sm'>No pending requests or invitations.</p>
        </div>
        <Button variant='outline' size='sm' className='mt-2' onClick={onInvite}>
          <UserPlus className='mr-2 h-4 w-4' />
          Invite an endpoint
        </Button>
      </Card>
    );
  }

  return (
    <div className='space-y-8'>
      {requests.length > 0 && (
        <PendingSection
          title='Needs your review'
          hint='endpoint owners asking to join'
          count={requests.length}
        >
          {requests.map((request) => (
            <PendingRow
              key={request.id}
              member={request}
              variant='inbound'
              actions={
                <div className='flex gap-2'>
                  <Button
                    size='sm'
                    disabled={reviewRequest.isPending}
                    onClick={() => {
                      reviewRequest.mutate({
                        collectiveId,
                        endpointId: request.endpoint_id,
                        decision: 'approve'
                      });
                    }}
                  >
                    <Check className='mr-1 h-4 w-4' />
                    Approve
                  </Button>
                  <Button
                    size='sm'
                    variant='outline'
                    disabled={reviewRequest.isPending}
                    onClick={() => {
                      reviewRequest.mutate({
                        collectiveId,
                        endpointId: request.endpoint_id,
                        decision: 'reject'
                      });
                    }}
                  >
                    Reject
                  </Button>
                </div>
              }
            />
          ))}
        </PendingSection>
      )}

      {invitations.length > 0 && (
        <PendingSection
          title='Awaiting response'
          hint='invitations you sent'
          count={invitations.length}
        >
          {invitations.map((invitation) => (
            <PendingRow
              key={invitation.id}
              member={invitation}
              variant='outbound'
              actions={
                <div className='flex items-center gap-3'>
                  <span className='flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400'>
                    <Clock className='h-3.5 w-3.5' />
                    Pending their reply
                  </span>
                  <Button
                    size='sm'
                    variant='ghost'
                    disabled={removeMember.isPending}
                    className='text-muted-foreground hover:text-destructive'
                    title='Cancel invitation'
                    onClick={() => {
                      removeMember.mutate({
                        collectiveId,
                        endpointId: invitation.endpoint_id
                      });
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              }
            />
          ))}
        </PendingSection>
      )}
    </div>
  );
}

/**
 * A labelled group inside the Pending tab. The uppercase header + count states
 * whose move it is; member rows are collected into one bordered, divided card
 * (rather than separate floating cards) so the group reads as a single queue.
 */
function PendingSection({
  title,
  hint,
  count,
  children
}: Readonly<{ title: string; hint: string; count: number; children: ReactNode }>) {
  return (
    <section>
      <div className='mb-3 flex items-baseline justify-between gap-3'>
        <h2 className='text-muted-foreground flex items-center gap-2 text-xs font-semibold tracking-wider uppercase'>
          {title}
          <span className='bg-primary/10 text-primary rounded-full px-2 py-0.5 text-[11px] font-medium'>
            {count}
          </span>
        </h2>
        <span className='text-muted-foreground text-xs'>{hint}</span>
      </div>
      <Card className='divide-border gap-0 divide-y overflow-hidden p-0'>{children}</Card>
    </section>
  );
}

/**
 * A single pending-membership row. The direction glyph (inbound ↘ / outbound ↗)
 * reinforces the section grouping; on narrow screens the actions wrap below the
 * endpoint info, indented past the glyph.
 */
function PendingRow({
  member,
  variant,
  actions
}: Readonly<{
  member: CollectiveMember;
  variant: 'inbound' | 'outbound';
  actions: ReactNode;
}>) {
  const DirectionIcon = variant === 'inbound' ? ArrowDownLeft : ArrowUpRight;
  const verb = variant === 'inbound' ? 'requested' : 'invited';
  return (
    <div className='flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center'>
      <div className='flex min-w-0 flex-1 items-center gap-3'>
        <div className='bg-muted text-muted-foreground shrink-0 rounded-md p-1.5' aria-hidden>
          <DirectionIcon className='h-4 w-4' />
        </div>
        <div className='min-w-0'>
          <p className='text-foreground truncate text-sm font-medium'>
            {member.endpoint_name ?? `Endpoint #${member.endpoint_id}`}
          </p>
          <p className='text-muted-foreground truncate text-xs'>
            {member.endpoint_owner_username
              ? `@${member.endpoint_owner_username}`
              : 'owner unknown'}
            {member.endpoint_type ? ` · ${member.endpoint_type}` : ''} · {verb}{' '}
            {formatRelativeTime(member.requested_at)}
          </p>
        </div>
      </div>
      <div className='shrink-0 pl-10 sm:pl-0'>{actions}</div>
    </div>
  );
}

/**
 * A pending pick in the invite modal: either one endpoint, or every joinable
 * endpoint of an owner (the `owner/*` action, expanded to slugs at pick time).
 */
type StagedInvite =
  | { kind: 'endpoint'; owner: string; slug: string; name: string }
  | { kind: 'all'; owner: string; endpoints: { slug: string; name: string }[] };

/**
 * Modal for inviting endpoints into the collective.
 *
 * A chat-style combobox lets the owner search owners/endpoints and Tab to
 * complete, or stage every endpoint of an owner at once (`owner/*`). Picks are
 * collected as removable chips and sent as one batch; only data-source
 * endpoints are ever surfaced (matching the backend join guard).
 */
function InviteEndpointModal({
  isOpen,
  collective,
  onClose,
  onInvited
}: Readonly<{
  isOpen: boolean;
  collective: Collective;
  onClose: () => void;
  onInvited: () => void;
}>) {
  const [staged, setStaged] = useState<StagedInvite[]>([]);
  const [result, setResult] = useState<InviteEndpointsByPathResult | null>(null);
  const inviteMany = useInviteEndpointsByPath();
  const resetInvite = inviteMany.reset;

  // Reset when the modal closes so reopening starts fresh. Depend on the stable
  // `reset` method, not the mutation object (which is a fresh ref each render).
  useEffect(() => {
    if (!isOpen) {
      setStaged([]);
      setResult(null);
      resetInvite();
    }
  }, [isOpen, resetInvite]);

  // Derive everything the modal/combobox needs from `staged` in one pass:
  // the staged endpoint keys + owner-wide picks (for the combobox's "already
  // staged" gating) and the deduplicated flat `{owner, slug}` targets to send.
  const { stagedKeys, stagedAllOwners, targets } = useMemo(() => {
    const keys = new Set<string>();
    const allOwners = new Set<string>();
    const targetMap = new Map<string, { owner: string; slug: string }>();
    for (const item of staged) {
      if (item.kind === 'endpoint') {
        keys.add(`${item.owner}/${item.slug}`);
        targetMap.set(`${item.owner}/${item.slug}`, { owner: item.owner, slug: item.slug });
      } else {
        allOwners.add(item.owner);
        for (const endpoint of item.endpoints) {
          targetMap.set(`${item.owner}/${endpoint.slug}`, {
            owner: item.owner,
            slug: endpoint.slug
          });
        }
      }
    }
    return { stagedKeys: keys, stagedAllOwners: allOwners, targets: [...targetMap.values()] };
  }, [staged]);

  const addEndpoint = (option: InviteEndpointOption) => {
    if (stagedAllOwners.has(option.owner)) return;
    if (stagedKeys.has(`${option.owner}/${option.slug}`)) return;
    setStaged((previous) => [...previous, { kind: 'endpoint', ...option }]);
  };

  const addAll = (owner: string, endpoints: { slug: string; name: string }[]) => {
    // An owner-wide pick supersedes any individual picks for that owner.
    setStaged((previous) => [
      ...previous.filter((item) => item.owner !== owner),
      { kind: 'all', owner, endpoints }
    ]);
  };

  const removeAt = (index: number) => {
    setStaged((previous) => previous.filter((_, index_) => index_ !== index));
  };

  const handleSend = () => {
    if (targets.length === 0) return;
    setResult(null);
    inviteMany.mutate(
      { collectiveId: collective.id, targets },
      {
        onSuccess: (response) => {
          if (response.failed.length === 0) {
            onInvited();
            return;
          }
          // Partial result — keep the modal open with a summary; clear staging
          // since the successes are sent and the failures are typically
          // "already a member" (not retryable).
          setResult(response);
          setStaged([]);
        }
      }
    );
  };

  const sendLabel = inviteMany.isPending
    ? 'Sending…'
    : `Send ${targets.length} invitation${targets.length === 1 ? '' : 's'}`;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title='Invite endpoints'>
      <div className='space-y-4'>
        <div>
          <Label htmlFor='invite-combobox-input'>Find endpoints</Label>
          <div className='mt-1'>
            <InviteCombobox
              onSelectEndpoint={addEndpoint}
              onSelectAll={addAll}
              stagedKeys={stagedKeys}
              stagedAllOwners={stagedAllOwners}
            />
          </div>
          <p className='text-muted-foreground mt-1 text-xs'>
            Search by owner to invite all their data sources, or pick individual endpoints. Each
            owner receives an email and decides whether to accept.
          </p>
        </div>

        {staged.length > 0 && (
          <div>
            <p className='text-muted-foreground mb-2 text-xs font-medium'>
              Staged invitations · {targets.length}
            </p>
            <div className='flex flex-wrap gap-2'>
              {staged.map((item, index) => (
                <span
                  key={item.kind === 'all' ? `all:${item.owner}` : `${item.owner}/${item.slug}`}
                  className='border-border bg-muted text-foreground inline-flex items-center gap-1.5 rounded-full border py-1 pr-1 pl-2.5 text-xs'
                >
                  {item.kind === 'all'
                    ? `@${item.owner} · all (${item.endpoints.length})`
                    : `@${item.owner}/${item.slug}`}
                  <button
                    type='button'
                    aria-label='Remove'
                    onClick={() => {
                      removeAt(index);
                    }}
                    className='text-muted-foreground hover:text-destructive flex h-4 w-4 items-center justify-center rounded-full'
                  >
                    <X className='h-3 w-3' />
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}

        {result && (
          <div className='text-sm'>
            {result.succeeded.length > 0 && (
              <p className='flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400'>
                <Check className='h-4 w-4' />
                {result.succeeded.length} invitation
                {result.succeeded.length === 1 ? '' : 's'} sent.
              </p>
            )}
            {result.failed.length > 0 && (
              <div className='text-muted-foreground mt-2'>
                <p>
                  {result.failed.length} couldn't be invited (e.g. already a member or invited):
                </p>
                <ul className='mt-1 space-y-0.5'>
                  {result.failed.map((failure) => (
                    <li key={`${failure.owner}/${failure.slug}`}>
                      <code>
                        {failure.owner}/{failure.slug}
                      </code>{' '}
                      — {failure.error.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className='flex justify-end gap-2 pt-2'>
          <Button variant='outline' onClick={onClose}>
            {result ? 'Close' : 'Cancel'}
          </Button>
          <Button disabled={targets.length === 0 || inviteMany.isPending} onClick={handleSend}>
            <Mail className='mr-2 h-4 w-4' />
            {sendLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/** General-settings form + danger zone for the collective. */
function CollectiveSettingsForm({ collective }: Readonly<{ collective: Collective }>) {
  const navigate = useNavigate();
  const updateCollective = useUpdateCollective();
  const deleteCollective = useDeleteCollective();

  const [name, setName] = useState(collective.name);
  const [description, setDescription] = useState(collective.description);
  const [about, setAbout] = useState(collective.about);
  const [iconUrl, setIconUrl] = useState(collective.icon_url ?? '');
  const [tags, setTags] = useState(collective.tags.join(', '));
  const [autoApprove, setAutoApprove] = useState(collective.auto_approve);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const handleSave = () => {
    updateCollective.mutate({
      id: collective.id,
      input: {
        name: name.trim(),
        description: description.trim(),
        about: about.trim(),
        icon_url: iconUrl.trim() || null,
        auto_approve: autoApprove,
        tags: parseTags(tags)
      }
    });
  };

  const handleDelete = () => {
    deleteCollective.mutate(collective.id, {
      onSuccess: () => {
        void navigate('/browse?tab=collectives');
      }
    });
  };

  return (
    <div className='space-y-6'>
      <Card className='p-6'>
        <h3 className='mb-4 text-lg font-semibold'>General</h3>
        <div className='space-y-4'>
          <div>
            <Label htmlFor='name'>Collective name</Label>
            <Input
              id='name'
              value={name}
              onChange={(e) => {
                setName(e.target.value);
              }}
              className='mt-1'
            />
          </div>
          <div>
            <Label htmlFor='description'>Description</Label>
            <Textarea
              id='description'
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
              }}
              rows={3}
              className='mt-1'
            />
            <p className='text-muted-foreground mt-1 text-xs'>
              Short summary shown on cards and the detail header.
            </p>
          </div>
          <div>
            <Label htmlFor='about'>About</Label>
            <Textarea
              id='about'
              value={about}
              onChange={(e) => {
                setAbout(e.target.value);
              }}
              rows={8}
              placeholder='# About this collective&#10;&#10;Long-form description — supports markdown.'
              className='mt-1 font-mono text-sm'
            />
            <p className='text-muted-foreground mt-1 text-xs'>
              Long-form markdown, shown as the "About" card on the detail page.
            </p>
          </div>
          <div>
            <Label htmlFor='icon'>Icon URL</Label>
            <Input
              id='icon'
              value={iconUrl}
              onChange={(e) => {
                setIconUrl(e.target.value);
              }}
              placeholder='https://example.com/icon.png'
              className='mt-1'
            />
          </div>
          <div>
            <Label htmlFor='tags'>Tags</Label>
            <Input
              id='tags'
              value={tags}
              onChange={(e) => {
                setTags(e.target.value);
              }}
              placeholder='healthcare, genomics, research'
              className='mt-1'
            />
            <p className='text-muted-foreground mt-1 text-xs'>
              Comma-separated, lowercase, up to 10 tags.
            </p>
          </div>
        </div>
      </Card>

      <Card className='p-6'>
        <h3 className='mb-4 text-lg font-semibold'>Membership</h3>
        <div className='flex items-start gap-3'>
          <Switch id='auto-approve' checked={autoApprove} onCheckedChange={setAutoApprove} />
          <div>
            <Label htmlFor='auto-approve'>Auto-approve join requests</Label>
            <p className='text-muted-foreground mt-1 text-sm'>
              When on, endpoints join immediately. When off, you review each request.
            </p>
          </div>
        </div>
      </Card>

      {updateCollective.isError && (
        <p className='text-destructive text-sm'>
          {updateCollective.error instanceof Error
            ? updateCollective.error.message
            : 'Failed to save'}
        </p>
      )}

      <div className='flex items-center justify-between'>
        <Button
          variant='outline'
          className='text-destructive hover:text-destructive'
          onClick={() => {
            setShowDeleteModal(true);
          }}
        >
          <Trash2 className='mr-2 h-4 w-4' />
          Delete collective
        </Button>
        <Button onClick={handleSave} disabled={updateCollective.isPending}>
          {updateCollective.isPending ? 'Saving...' : 'Save changes'}
        </Button>
      </div>

      <Modal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
        }}
        title={`Delete ${collective.name}?`}
      >
        <div className='space-y-4'>
          <p className='text-muted-foreground text-sm'>
            This permanently deletes the collective and all its memberships. The endpoints
            themselves are not affected. This cannot be undone.
          </p>
          {deleteCollective.isError && (
            <p className='text-destructive text-sm'>
              {deleteCollective.error instanceof Error
                ? deleteCollective.error.message
                : 'Failed to delete'}
            </p>
          )}
          <div className='flex justify-end gap-2'>
            <Button
              variant='outline'
              onClick={() => {
                setShowDeleteModal(false);
              }}
            >
              Cancel
            </Button>
            <Button
              variant='destructive'
              onClick={handleDelete}
              disabled={deleteCollective.isPending}
            >
              {deleteCollective.isPending ? 'Deleting...' : 'Delete collective'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
