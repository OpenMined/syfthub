import { useEffect, useMemo, useState } from 'react';

import type {
  Collective,
  CollectiveMember,
  CollectiveSharedEndpoint,
  CollectiveSharedEndpointMember
} from '@/lib/collectives-api';

import AlertTriangle from 'lucide-react/dist/esm/icons/alert-triangle';
import Check from 'lucide-react/dist/esm/icons/check';
import Copy from 'lucide-react/dist/esm/icons/copy';
import Database from 'lucide-react/dist/esm/icons/database';
import Pencil from 'lucide-react/dist/esm/icons/pencil';
import Plus from 'lucide-react/dist/esm/icons/plus';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Modal } from '@/components/ui/modal';
import { Textarea } from '@/components/ui/textarea';
import {
  useCreateSharedEndpoint,
  useDeleteSharedEndpoint,
  useSharedEndpoints,
  useUpdateSharedEndpoint
} from '@/hooks/use-shared-endpoints';

interface SharedEndpointsTabProperties {
  collective: Collective;
  /** Currently approved member endpoints — used to populate the picker. */
  approvedMembers: CollectiveMember[];
}

/**
 * Admin tab listing a collective's shared endpoints (named, curated subsets
 * of approved members) with create / edit / delete affordances.
 *
 * When a configured endpoint later leaves the collective the row stays in the
 * shared endpoint (and is silently dropped from chat fan-out); we surface
 * that as an "inactive" badge so owners can either re-invite the endpoint
 * or remove it from the subset.
 */
export function SharedEndpointsTab({
  collective,
  approvedMembers
}: Readonly<SharedEndpointsTabProperties>) {
  const { data: sharedEndpoints, isLoading } = useSharedEndpoints(collective.id);
  const [modalState, setModalState] = useState<
    { mode: 'create' } | { mode: 'edit'; shared: CollectiveSharedEndpoint } | null
  >(null);

  const noMembers = approvedMembers.length === 0;

  return (
    <div className='space-y-4'>
      <div className='flex items-center justify-between'>
        <div>
          <h2 className='font-rubik text-foreground text-lg font-medium'>Shared Endpoints</h2>
          <p className='text-muted-foreground text-sm'>
            Curated subsets of this collective's approved members. Each one is addressable as{' '}
            <code>{collective.shared_endpoint_path}/&lt;slug&gt;</code>.
          </p>
        </div>
        <Button
          onClick={() => {
            setModalState({ mode: 'create' });
          }}
          disabled={noMembers}
          title={
            noMembers
              ? 'Approve at least one member endpoint before creating a shared endpoint'
              : undefined
          }
        >
          <Plus className='mr-2 h-4 w-4' />
          New shared endpoint
        </Button>
      </div>

      {/* Default-all row pinned at the top — not a stored entity, just a
          shortcut so owners can see and copy the implicit catch-all path. */}
      <DefaultAllRow collective={collective} approvedMemberCount={approvedMembers.length} />

      <SharedEndpointsList
        collective={collective}
        sharedEndpoints={sharedEndpoints ?? []}
        isLoading={isLoading}
        noMembers={noMembers}
        onEdit={(shared) => {
          setModalState({ mode: 'edit', shared });
        }}
      />

      {modalState != null && (
        <SharedEndpointModal
          collective={collective}
          approvedMembers={approvedMembers}
          mode={modalState.mode}
          existing={modalState.mode === 'edit' ? modalState.shared : null}
          onClose={() => {
            setModalState(null);
          }}
        />
      )}
    </div>
  );
}

interface DefaultAllRowProperties {
  collective: Collective;
  approvedMemberCount: number;
}

interface SharedEndpointsListProperties {
  collective: Collective;
  sharedEndpoints: CollectiveSharedEndpoint[];
  isLoading: boolean;
  noMembers: boolean;
  onEdit: (shared: CollectiveSharedEndpoint) => void;
}

/**
 * Body of the tab: a loading spinner, an empty-state card, or the list of
 * shared-endpoint rows. Extracted so the parent stays a thin shell and the
 * nested-ternary lint rule is satisfied.
 */
function SharedEndpointsList({
  collective,
  sharedEndpoints,
  isLoading,
  noMembers,
  onEdit
}: Readonly<SharedEndpointsListProperties>) {
  if (isLoading) {
    return (
      <div className='flex justify-center py-12'>
        <LoadingSpinner />
      </div>
    );
  }
  if (sharedEndpoints.length === 0) {
    return (
      <Card className='text-muted-foreground p-12 text-center text-sm'>
        {noMembers
          ? 'Approve at least one data-source endpoint to start creating shared subsets.'
          : 'No custom shared endpoints yet. Create one to fan out chats to a specific subset of members.'}
      </Card>
    );
  }
  return (
    <div className='space-y-3'>
      {sharedEndpoints.map((shared) => (
        <SharedEndpointRow
          key={shared.id}
          collective={collective}
          shared={shared}
          onEdit={() => {
            onEdit(shared);
          }}
        />
      ))}
    </div>
  );
}

/**
 * Static row representing the implicit ``collective/<slug>/all`` shortcut.
 *
 * This is NOT a database row — the backend short-circuits the ``all`` slug
 * to "every approved member" and the SDK normalises it away — so the row is
 * purely informational and has no edit/delete affordances.
 */
function DefaultAllRow({ collective, approvedMemberCount }: Readonly<DefaultAllRowProperties>) {
  return (
    <Card className='border-border/60 bg-muted/20 p-4'>
      <div className='flex items-start gap-4'>
        <div className='bg-primary/10 text-primary mt-0.5 rounded-md p-2'>
          <Database className='h-5 w-5' />
        </div>
        <div className='min-w-0 flex-1'>
          <div className='flex flex-wrap items-center gap-2'>
            <p className='font-inter text-foreground font-medium'>All members</p>
            <Badge variant='secondary'>default</Badge>
          </div>
          <p className='text-muted-foreground mt-0.5 text-xs'>
            Fans out to every approved endpoint in the collective.
          </p>
          <CopyPath path={`${collective.shared_endpoint_path}/all`} className='mt-2' />
        </div>
        <div className='text-muted-foreground shrink-0 text-right text-xs'>
          {approvedMemberCount} active
        </div>
      </div>
    </Card>
  );
}

interface SharedEndpointRowProperties {
  collective: Collective;
  shared: CollectiveSharedEndpoint;
  onEdit: () => void;
}

function SharedEndpointRow({ collective, shared, onEdit }: Readonly<SharedEndpointRowProperties>) {
  const deleteMutation = useDeleteSharedEndpoint();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const inactiveCount = shared.member_count - shared.active_member_count;

  return (
    <Card className='p-4'>
      <div className='flex items-start gap-4'>
        <div className='bg-primary/10 text-primary mt-0.5 rounded-md p-2'>
          <Database className='h-5 w-5' />
        </div>
        <div className='min-w-0 flex-1'>
          <div className='flex flex-wrap items-center gap-2'>
            <p className='font-inter text-foreground font-medium'>{shared.name}</p>
            {inactiveCount > 0 && (
              <Badge
                variant='outline'
                className='border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-300'
              >
                <AlertTriangle className='mr-1 h-3 w-3' />
                {inactiveCount} inactive
              </Badge>
            )}
          </div>
          {shared.description && (
            <p className='text-muted-foreground mt-0.5 text-xs'>{shared.description}</p>
          )}
          <CopyPath path={shared.shared_endpoint_path} className='mt-2' />
        </div>
        <div className='flex shrink-0 items-center gap-2 text-right'>
          <div className='text-muted-foreground text-xs'>
            <p>
              <span className='text-foreground font-medium'>{shared.active_member_count}</span> /{' '}
              {shared.member_count} active
            </p>
          </div>
          <Button size='sm' variant='ghost' onClick={onEdit} title='Edit'>
            <Pencil className='h-4 w-4' />
          </Button>
          <Button
            size='sm'
            variant='ghost'
            onClick={() => {
              setConfirmDelete(true);
            }}
            title='Delete'
            className='text-muted-foreground hover:text-destructive'
          >
            <Trash2 className='h-4 w-4' />
          </Button>
        </div>
      </div>

      {confirmDelete && (
        <Modal
          isOpen
          onClose={() => {
            setConfirmDelete(false);
          }}
          title='Delete shared endpoint?'
        >
          <div className='space-y-3 text-sm'>
            <p>
              This removes <code>{shared.shared_endpoint_path}</code> as a routing alias. Member
              endpoints themselves are NOT affected — they remain in the collective.
            </p>
            {deleteMutation.isError && (
              <p className='text-destructive'>
                {deleteMutation.error instanceof Error
                  ? deleteMutation.error.message
                  : 'Failed to delete'}
              </p>
            )}
            <div className='flex justify-end gap-2 pt-2'>
              <Button
                variant='outline'
                onClick={() => {
                  setConfirmDelete(false);
                }}
              >
                Cancel
              </Button>
              <Button
                variant='destructive'
                disabled={deleteMutation.isPending}
                onClick={() => {
                  deleteMutation.mutate(
                    {
                      collectiveId: collective.id,
                      sharedSlug: shared.slug,
                      collectiveSlug: collective.slug
                    },
                    {
                      onSuccess: () => {
                        setConfirmDelete(false);
                      }
                    }
                  );
                }}
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </Card>
  );
}

interface SharedEndpointModalProperties {
  collective: Collective;
  approvedMembers: CollectiveMember[];
  mode: 'create' | 'edit';
  existing: CollectiveSharedEndpoint | null;
  onClose: () => void;
}

/**
 * Create/edit modal for a shared endpoint.
 *
 * Slug is editable on create (with a name-derived preview that locks when the
 * user edits it) and immutable on edit — renaming the slug would silently
 * break callers using the public path.
 */
function SharedEndpointModal({
  collective,
  approvedMembers,
  mode,
  existing,
  onClose
}: Readonly<SharedEndpointModalProperties>) {
  const isEdit = mode === 'edit';
  const [name, setName] = useState(existing?.name ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [slug, setSlug] = useState(existing?.slug ?? '');
  const [slugLocked, setSlugLocked] = useState(isEdit);
  const initialIds = useMemo(
    () =>
      new Set(
        (existing?.members ?? [])
          .filter((member) => member.is_active)
          .map((member) => member.endpoint_id)
      ),
    [existing]
  );
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<number>>(initialIds);

  const createMutation = useCreateSharedEndpoint();
  const updateMutation = useUpdateSharedEndpoint();

  // Live-derive the slug from the name until the user types into the slug
  // field; mirrors the create-collective wizard's behaviour.
  useEffect(() => {
    if (isEdit) return;
    if (slugLocked) return;
    setSlug(slugify(name));
  }, [name, isEdit, slugLocked]);

  const inactiveExistingMembers: CollectiveSharedEndpointMember[] = useMemo(
    () => (existing?.members ?? []).filter((member) => !member.is_active),
    [existing]
  );

  const toggleEndpoint = (endpointId: number) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(endpointId)) {
        next.delete(endpointId);
      } else {
        next.add(endpointId);
      }
      return next;
    });
  };

  const handleSubmit = () => {
    const trimmedName = name.trim();
    if (!trimmedName) return;
    const endpointIds = [...selectedIds];
    if (isEdit && existing != null) {
      updateMutation.mutate(
        {
          collectiveId: collective.id,
          sharedSlug: existing.slug,
          input: {
            name: trimmedName,
            description: description.trim(),
            endpoint_ids: endpointIds
          }
        },
        { onSuccess: onClose }
      );
    } else {
      createMutation.mutate(
        {
          collectiveId: collective.id,
          input: {
            name: trimmedName,
            description: description.trim(),
            slug: slug.trim() || undefined,
            endpoint_ids: endpointIds
          }
        },
        { onSuccess: onClose }
      );
    }
  };

  const isSubmitting = createMutation.isPending || updateMutation.isPending;
  const submitError = createMutation.error ?? updateMutation.error;
  const canSubmit = name.trim().length > 0 && selectedIds.size > 0 && !isSubmitting;

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={isEdit ? `Edit ${existing?.name ?? 'shared endpoint'}` : 'New shared endpoint'}
    >
      <div className='space-y-4'>
        <div>
          <Label htmlFor='shared-endpoint-name'>Name</Label>
          <Input
            id='shared-endpoint-name'
            value={name}
            onChange={(event) => {
              setName(event.target.value);
            }}
            placeholder='Health News'
            className='mt-1'
            maxLength={100}
          />
        </div>

        <div>
          <Label htmlFor='shared-endpoint-slug'>Slug</Label>
          <Input
            id='shared-endpoint-slug'
            value={slug}
            onChange={(event) => {
              setSlug(event.target.value);
              setSlugLocked(true);
            }}
            disabled={isEdit}
            placeholder='health-news'
            className='mt-1 font-mono text-sm'
            maxLength={63}
          />
          <p className='text-muted-foreground mt-1 text-xs'>
            Public path:{' '}
            <code>
              {collective.shared_endpoint_path}/{slug || '<slug>'}
            </code>
            {isEdit && ' · slug is immutable after creation'}
          </p>
        </div>

        <div>
          <Label htmlFor='shared-endpoint-description'>Description</Label>
          <Textarea
            id='shared-endpoint-description'
            value={description}
            onChange={(event) => {
              setDescription(event.target.value);
            }}
            placeholder='One-line description of what this subset covers'
            className='mt-1'
            maxLength={500}
            rows={2}
          />
        </div>

        <div>
          <Label>Endpoints</Label>
          <p className='text-muted-foreground mt-1 mb-2 text-xs'>
            Pick which approved member endpoints to include. The shared endpoint fans out only to
            these at chat time.
          </p>
          <div className='border-border max-h-72 overflow-y-auto rounded-md border'>
            {approvedMembers.length === 0 ? (
              <p className='text-muted-foreground p-4 text-center text-sm'>
                No approved members yet.
              </p>
            ) : (
              approvedMembers.map((member) => {
                const checked = selectedIds.has(member.endpoint_id);
                return (
                  <label
                    key={member.endpoint_id}
                    className='hover:bg-muted/30 flex cursor-pointer items-start gap-3 border-b px-3 py-2 last:border-b-0'
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() => {
                        toggleEndpoint(member.endpoint_id);
                      }}
                      className='mt-0.5'
                    />
                    <div className='min-w-0 flex-1'>
                      <p className='text-sm font-medium'>
                        {member.endpoint_name ?? `#${member.endpoint_id}`}
                      </p>
                      <p className='text-muted-foreground truncate text-xs'>
                        {member.endpoint_owner_username
                          ? `@${member.endpoint_owner_username}/`
                          : ''}
                        {member.endpoint_slug ?? ''}
                        {member.endpoint_type ? ` · ${member.endpoint_type}` : ''}
                      </p>
                    </div>
                  </label>
                );
              })
            )}
          </div>
          <p className='text-muted-foreground mt-1 text-xs'>
            {selectedIds.size} of {approvedMembers.length} selected
          </p>
        </div>

        {inactiveExistingMembers.length > 0 && (
          <InactiveMembersNotice members={inactiveExistingMembers} />
        )}

        {submitError != null && (
          <p className='text-destructive text-sm'>
            {submitError instanceof Error ? submitError.message : 'Failed to save'}
          </p>
        )}

        <div className='flex justify-end gap-2 pt-2'>
          <Button variant='outline' onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button disabled={!canSubmit} onClick={handleSubmit}>
            {submitLabel(isSubmitting, isEdit)}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/**
 * Surfaces configured endpoints that have since left the collective.
 *
 * These rows still exist in the shared endpoint but are silently dropped
 * from chat fan-out. The owner needs to decide whether to re-invite them
 * or remove them from the selection (saving the modal with them unselected
 * persists the removal).
 */
function InactiveMembersNotice({
  members
}: Readonly<{ members: CollectiveSharedEndpointMember[] }>) {
  return (
    <Card className='border-amber-500/40 bg-amber-500/5 p-3'>
      <div className='flex items-start gap-2 text-sm'>
        <AlertTriangle className='mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400' />
        <div className='min-w-0 flex-1'>
          <p className='font-medium'>Some configured endpoints have left the collective.</p>
          <p className='text-muted-foreground mt-1 text-xs'>
            They're skipped at fan-out time. Re-invite them in the Members tab or save this modal to
            remove them from the selection.
          </p>
          <ul className='text-muted-foreground mt-2 space-y-0.5 text-xs'>
            {members.map((member) => (
              <li key={member.endpoint_id}>
                <code>
                  {member.endpoint_owner_username ? `${member.endpoint_owner_username}/` : ''}
                  {member.endpoint_slug ?? `#${member.endpoint_id}`}
                </code>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

interface CopyPathProperties {
  path: string;
  className?: string;
}

function CopyPath({ path, className }: Readonly<CopyPathProperties>) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type='button'
      onClick={() => {
        void navigator.clipboard.writeText(path).then(() => {
          setCopied(true);
          setTimeout(() => {
            setCopied(false);
          }, 1500);
        });
      }}
      className={`hover:bg-muted/50 inline-flex items-center gap-2 rounded-md border px-2 py-1 font-mono text-xs ${className ?? ''}`}
    >
      <code className='truncate'>{path}</code>
      {copied ? (
        <Check className='h-3 w-3 text-emerald-500' />
      ) : (
        <Copy className='h-3 w-3 opacity-60' />
      )}
    </button>
  );
}

/** Submit-button label for the create/edit modal. */
function submitLabel(isSubmitting: boolean, isEdit: boolean): string {
  if (isSubmitting) return 'Saving...';
  return isEdit ? 'Save changes' : 'Create';
}

/**
 * Local slugifier for the live name -> slug preview. Mirrors the backend
 * helper closely enough to be honest; the server is the source of truth and
 * rejects malformed slugs at create time.
 *
 * Walks the string segment-by-segment rather than using a greedy `+`
 * quantifier so sonarjs/slow-regex doesn't flag it as potentially super-linear.
 */
function slugify(value: string): string {
  const lowered = value.toLowerCase();
  const segments: string[] = [];
  let current = '';
  for (const char of lowered) {
    if (/^[a-z0-9]$/.test(char)) {
      current += char;
    } else if (current) {
      segments.push(current);
      current = '';
    }
  }
  if (current) segments.push(current);
  let slug = segments.join('-');
  if (slug.length > 63) slug = slug.slice(0, 63);
  while (slug.endsWith('-')) slug = slug.slice(0, -1);
  return slug;
}
