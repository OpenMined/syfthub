import { useState } from 'react';

import type { Collective } from '@/lib/collectives-api';

import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';
import UserCheck from 'lucide-react/dist/esm/icons/user-check';
import UserX from 'lucide-react/dist/esm/icons/user-x';
import Users from 'lucide-react/dist/esm/icons/users';
import { Link, useNavigate, useParams } from 'react-router-dom';

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
  useRemoveMember,
  useReviewRequest,
  useUpdateCollective
} from '@/hooks/use-collectives';
import { formatDate } from '@/lib/date-utils';

type AdminTab = 'members' | 'requests' | 'settings';

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
      <div className='container mx-auto px-6 py-16 text-center'>
        <h1 className='mb-4 text-2xl font-bold'>Collective not found</h1>
        <Button asChild>
          <Link to='/collectives/browse'>Browse collectives</Link>
        </Button>
      </div>
    );
  }

  const isOwner = user != null && Number(user.id) === collective.owner_id;
  if (!isOwner) {
    return (
      <div className='container mx-auto px-6 py-16 text-center'>
        <h1 className='mb-4 text-2xl font-bold'>Access denied</h1>
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

  const { data: approvedMembers } = useCollectiveMembers(collective.id, 'approved');
  const { data: pendingMembers } = useCollectiveMembers(collective.id, 'pending');
  const removeMember = useRemoveMember();
  const reviewRequest = useReviewRequest();

  const members = approvedMembers ?? [];
  const requests = pendingMembers ?? [];

  const tabs: { id: AdminTab; label: string; badge?: number }[] = [
    { id: 'members', label: 'Members' },
    { id: 'requests', label: 'Requests', badge: requests.length },
    { id: 'settings', label: 'Settings' }
  ];

  return (
    <div className='container mx-auto max-w-5xl px-6 py-8'>
      {/* Header */}
      <div className='mb-8'>
        <Link
          to={`/c/${collective.slug}`}
          className='text-muted-foreground hover:text-foreground mb-4 inline-flex items-center gap-2 text-sm'
        >
          <ArrowLeft className='h-4 w-4' />
          Back to {collective.name}
        </Link>
        <h1 className='flex items-center gap-2 text-3xl font-bold'>
          Manage {collective.name}
          {collective.verified && (
            <CheckCircle className='h-6 w-6 text-green-500' aria-label='Verified collective' />
          )}
        </h1>
        <p className='text-muted-foreground mt-1'>
          Administer this collective's members, join requests and settings
        </p>
      </div>

      {/* Quick stats */}
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

      {/* Tabs */}
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

      {/* Members */}
      {activeTab === 'members' && (
        <div className='space-y-3'>
          {members.length > 0 ? (
            members.map((member) => (
              <Card key={member.id} className='p-4'>
                <div className='flex items-center justify-between gap-3'>
                  <div className='min-w-0'>
                    <p className='truncate font-medium'>
                      {member.endpoint_name ?? `Endpoint #${member.endpoint_id}`}
                    </p>
                    <p className='text-muted-foreground text-xs'>
                      {member.endpoint_owner_username
                        ? `@${member.endpoint_owner_username}`
                        : 'owner unknown'}
                      {member.endpoint_type ? ` · ${member.endpoint_type}` : ''}
                    </p>
                  </div>
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
                  >
                    <UserX className='h-4 w-4' />
                  </Button>
                </div>
              </Card>
            ))
          ) : (
            <Card className='text-muted-foreground p-12 text-center text-sm'>
              No approved endpoints yet.
            </Card>
          )}
        </div>
      )}

      {/* Requests */}
      {activeTab === 'requests' && (
        <div className='space-y-3'>
          {requests.length > 0 ? (
            requests.map((request) => (
              <Card key={request.id} className='p-4'>
                <div className='flex items-center justify-between gap-3'>
                  <div className='min-w-0'>
                    <p className='truncate font-medium'>
                      {request.endpoint_name ?? `Endpoint #${request.endpoint_id}`}
                    </p>
                    <p className='text-muted-foreground text-xs'>
                      {request.endpoint_owner_username
                        ? `@${request.endpoint_owner_username}`
                        : 'owner unknown'}{' '}
                      · requested {formatDate(request.requested_at)}
                    </p>
                  </div>
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
                </div>
              </Card>
            ))
          ) : (
            <Card className='text-muted-foreground p-12 text-center text-sm'>
              No pending join requests.
            </Card>
          )}
        </div>
      )}

      {/* Settings */}
      {activeTab === 'settings' && <CollectiveSettingsForm collective={collective} />}
    </div>
  );
}

/** General-settings form + danger zone for the collective. */
function CollectiveSettingsForm({ collective }: Readonly<{ collective: Collective }>) {
  const navigate = useNavigate();
  const updateCollective = useUpdateCollective();
  const deleteCollective = useDeleteCollective();

  const [name, setName] = useState(collective.name);
  const [description, setDescription] = useState(collective.description);
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
        icon_url: iconUrl.trim() || null,
        auto_approve: autoApprove,
        tags: tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean)
      }
    });
  };

  const handleDelete = () => {
    deleteCollective.mutate(collective.id, {
      onSuccess: () => {
        void navigate('/collectives/browse');
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
              <CheckCircle className='h-3 w-3 text-green-500' />
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
