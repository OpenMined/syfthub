import { useEffect, useState } from 'react';

import type { Collective, CollectiveMember } from '@/lib/collectives-api';
import type { ChatSource } from '@/lib/types';
import type { ReactNode } from 'react';

import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import Mail from 'lucide-react/dist/esm/icons/mail';
import ShieldCheck from 'lucide-react/dist/esm/icons/shield-check';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';
import UserCheck from 'lucide-react/dist/esm/icons/user-check';
import UserPlus from 'lucide-react/dist/esm/icons/user-plus';
import UserX from 'lucide-react/dist/esm/icons/user-x';
import Users from 'lucide-react/dist/esm/icons/users';
import X from 'lucide-react/dist/esm/icons/x';
import { Link, useNavigate, useParams } from 'react-router-dom';

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
  useInviteEndpointByPath,
  useRemoveMember,
  useReviewRequest,
  useUpdateCollective
} from '@/hooks/use-collectives';
import { useEndpointByPath } from '@/hooks/use-endpoint-queries';
import { isJoinableEndpointType, parseTags } from '@/lib/collectives-api';
import { formatDate } from '@/lib/date-utils';

type AdminTab = 'members' | 'requests' | 'invitations' | 'shared' | 'settings';

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
    { id: 'requests', label: 'Requests', badge: requests.length },
    { id: 'invitations', label: 'Invitations', badge: invitations.length },
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
              <Badge variant='destructive' className='ml-2 text-xs'>
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

      {activeTab === 'requests' && (
        <div className='space-y-3'>
          {requests.length > 0 ? (
            requests.map((request) => (
              <MemberRow
                key={request.id}
                member={request}
                subtitle={
                  <>
                    {request.endpoint_owner_username
                      ? `@${request.endpoint_owner_username}`
                      : 'owner unknown'}{' '}
                    · requested {formatDate(request.requested_at)}
                  </>
                }
                actions={
                  <div className='flex shrink-0 gap-2'>
                    <Button
                      size='sm'
                      disabled={reviewRequest.isPending}
                      onClick={() => {
                        reviewRequest.mutate({
                          collectiveId: collective.id,
                          endpointId: request.endpoint_id,
                          decision: 'approve'
                        });
                      }}
                    >
                      <UserCheck className='mr-1 h-4 w-4' />
                      Approve
                    </Button>
                    <Button
                      size='sm'
                      variant='outline'
                      disabled={reviewRequest.isPending}
                      onClick={() => {
                        reviewRequest.mutate({
                          collectiveId: collective.id,
                          endpointId: request.endpoint_id,
                          decision: 'reject'
                        });
                      }}
                    >
                      <UserX className='mr-1 h-4 w-4' />
                      Reject
                    </Button>
                  </div>
                }
              />
            ))
          ) : (
            <Card className='text-muted-foreground p-12 text-center text-sm'>
              No pending join requests.
            </Card>
          )}
        </div>
      )}

      {activeTab === 'invitations' && (
        <div className='space-y-3'>
          {invitations.length > 0 ? (
            invitations.map((invitation) => (
              <MemberRow
                key={invitation.id}
                member={invitation}
                subtitle={
                  <>
                    {invitation.endpoint_owner_username
                      ? `@${invitation.endpoint_owner_username}`
                      : 'owner unknown'}{' '}
                    · invited {formatDate(invitation.requested_at)}
                  </>
                }
                actions={
                  <Button
                    size='sm'
                    variant='outline'
                    disabled={removeMember.isPending}
                    onClick={() => {
                      removeMember.mutate({
                        collectiveId: collective.id,
                        endpointId: invitation.endpoint_id
                      });
                    }}
                    title='Cancel invitation'
                  >
                    <X className='mr-1 h-4 w-4' />
                    Cancel
                  </Button>
                }
              />
            ))
          ) : (
            <Card className='text-muted-foreground p-12 text-center text-sm'>
              <Mail className='mx-auto mb-3 h-8 w-8 opacity-50' />
              <p>No pending invitations.</p>
              <p className='mt-2 text-xs'>
                Use the "Invite endpoint" button above to invite an endpoint by its
                <code className='mx-1'>owner/slug</code>
                path.
              </p>
            </Card>
          )}
        </div>
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
          setActiveTab('invitations');
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
 * Modal for inviting an endpoint into the collective by `owner/slug` path.
 *
 * The collective owner enters a path (e.g. `alice/genome-data`), we preview
 * the resolved endpoint via the public-by-path API, and on confirm send an
 * invitation. Only data-source endpoints are joinable; the modal blocks
 * submission when the resolved endpoint isn't eligible.
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
  const [path, setPath] = useState('');
  // Debounced path used for the actual lookup so we don't spam the API while
  // the user is still typing.
  const [debouncedPath, setDebouncedPath] = useState('');
  const inviteMutation = useInviteEndpointByPath();
  const resetInvite = inviteMutation.reset;

  useEffect(() => {
    const trimmed = path.trim();
    if (!trimmed) {
      setDebouncedPath('');
      return;
    }
    const timer = setTimeout(() => {
      setDebouncedPath(trimmed);
    }, 300);
    return () => {
      clearTimeout(timer);
    };
  }, [path]);

  // Reset when the modal closes so reopening starts fresh. Depend on the
  // stable `reset` method, not the mutation object — `useMutation` returns a
  // fresh result object every render, which would re-fire this effect on
  // every render.
  useEffect(() => {
    if (!isOpen) {
      setPath('');
      setDebouncedPath('');
      resetInvite();
    }
  }, [isOpen, resetInvite]);

  const parsed = parseOwnerSlug(debouncedPath);
  const { data: endpoint, isFetching: isResolving } = useEndpointByPath(
    parsed ? `${parsed.owner}/${parsed.slug}` : undefined
  );

  const ineligibleType = endpoint?.type != null && !isJoinableEndpointType(endpoint.type);

  const canSubmit =
    parsed != null && endpoint != null && !ineligibleType && !inviteMutation.isPending;

  const handleSubmit = () => {
    if (!parsed) return;
    inviteMutation.mutate(
      { collectiveId: collective.id, ownerUsername: parsed.owner, slug: parsed.slug },
      { onSuccess: onInvited }
    );
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title='Invite an endpoint'>
      <div className='space-y-4'>
        <div>
          <Label htmlFor='invite-path'>Endpoint path</Label>
          <Input
            id='invite-path'
            placeholder='owner/endpoint-slug'
            value={path}
            onChange={(e) => {
              setPath(e.target.value);
            }}
            className='mt-1 font-mono text-sm'
          />
          <p className='text-muted-foreground mt-1 text-xs'>
            Enter the public path of a data-source endpoint, e.g. <code>alice/genome-data</code>.
            The endpoint owner receives an email and decides whether to accept.
          </p>
        </div>

        <InvitePreview
          path={debouncedPath}
          parsed={parsed}
          endpoint={endpoint ?? null}
          isResolving={isResolving}
          ineligibleType={ineligibleType}
        />

        {inviteMutation.isError && (
          <p className='text-destructive text-sm'>
            {inviteMutation.error instanceof Error
              ? inviteMutation.error.message
              : 'Failed to send invitation'}
          </p>
        )}

        <div className='flex justify-end gap-2 pt-2'>
          <Button variant='outline' onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!canSubmit} onClick={handleSubmit}>
            <Mail className='mr-2 h-4 w-4' />
            {inviteMutation.isPending ? 'Sending...' : 'Send invitation'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/**
 * Render the resolved-endpoint preview block beneath the path input — empty
 * state, loading, error, mismatch, or a confirmed match.
 */
function InvitePreview({
  path,
  parsed,
  endpoint,
  isResolving,
  ineligibleType
}: Readonly<{
  path: string;
  parsed: { owner: string; slug: string } | null;
  endpoint: ChatSource | null;
  isResolving: boolean;
  ineligibleType: boolean;
}>) {
  if (!path) {
    return null;
  }
  if (!parsed) {
    return (
      <p className='text-destructive text-sm'>
        Path must look like <code>owner/endpoint-slug</code>.
      </p>
    );
  }
  if (isResolving) {
    return <p className='text-muted-foreground text-sm'>Looking up endpoint...</p>;
  }
  if (!endpoint) {
    return (
      <p className='text-destructive text-sm'>
        No public endpoint at{' '}
        <code>
          {parsed.owner}/{parsed.slug}
        </code>
        .
      </p>
    );
  }
  if (ineligibleType) {
    return (
      <Card className='border-destructive/30 bg-destructive/5 p-3 text-sm'>
        <p className='font-medium'>{endpoint.name}</p>
        <p className='text-muted-foreground text-xs'>
          @{endpoint.owner_username} · {endpoint.type}
        </p>
        <p className='text-destructive mt-2 text-xs'>
          Only data-source endpoints can join a collective.
        </p>
      </Card>
    );
  }
  return (
    <Card className='border-primary/30 bg-primary/5 p-3 text-sm'>
      <p className='font-medium'>{endpoint.name}</p>
      <p className='text-muted-foreground text-xs'>
        @{endpoint.owner_username} · {endpoint.type}
      </p>
      {endpoint.description && (
        <p className='text-muted-foreground mt-2 text-xs'>{endpoint.description}</p>
      )}
    </Card>
  );
}

function parseOwnerSlug(path: string): { owner: string; slug: string } | null {
  const trimmed = path.trim().replace(/^@/, '').replace(/^\//, '');
  if (!trimmed) return null;
  const parts = trimmed.split('/');
  if (parts.length !== 2) return null;
  const [owner, slug] = parts;
  if (!owner || !slug) return null;
  return { owner, slug };
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
        <div className='text-muted-foreground mt-4 flex items-center gap-2 border-t pt-4 text-sm'>
          <span>Verification:</span>
          {collective.verified ? (
            <Badge variant='secondary' className='gap-1'>
              <ShieldCheck className='h-3 w-3 text-green-500' />
              Verified
            </Badge>
          ) : (
            <Badge variant='outline'>Not verified</Badge>
          )}
          <span className='text-xs'>— granted by the platform, not editable here.</span>
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
