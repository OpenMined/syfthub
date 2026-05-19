import { useState } from 'react';

import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import ArrowRight from 'lucide-react/dist/esm/icons/arrow-right';
import Check from 'lucide-react/dist/esm/icons/check';
import Shield from 'lucide-react/dist/esm/icons/shield';
import Users from 'lucide-react/dist/esm/icons/users';
import { Link, useNavigate } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useCreateCollective } from '@/hooks/use-collectives';
import { parseTags } from '@/lib/collectives-api';
import { cn } from '@/lib/utils';

/** Derive a URL-safe slug preview from a name (the backend re-validates). */
function slugify(name: string): string {
  return name
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, '-')
    .replaceAll(/^-|-$/g, '');
}

const STEPS = [
  { id: 1, name: 'Details', icon: Users },
  { id: 2, name: 'Membership', icon: Shield },
  { id: 3, name: 'Review', icon: Check }
];

/**
 * Create-collective wizard (`/collectives/create`, auth-protected).
 *
 * Collects only fields the backend accepts (`CollectiveCreate`): name, slug,
 * description, icon, tags and the `auto_approve` join policy.
 */
export default function CreateCollectivePage() {
  const navigate = useNavigate();
  const createCollective = useCreateCollective();

  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [customSlug, setCustomSlug] = useState<string | null>(null);
  const [description, setDescription] = useState('');
  const [about, setAbout] = useState('');
  const [iconUrl, setIconUrl] = useState('');
  const [tags, setTags] = useState('');
  const [autoApprove, setAutoApprove] = useState(false);

  const slugPreview = customSlug ?? slugify(name);

  const handleCreate = () => {
    createCollective.mutate(
      {
        name: name.trim(),
        description: description.trim(),
        about: about.trim(),
        icon_url: iconUrl.trim() || null,
        auto_approve: autoApprove,
        tags: parseTags(tags),
        // Send the slug only when the user customized it; otherwise let the
        // backend derive (and de-duplicate) one from the name.
        ...(customSlug?.trim() ? { slug: customSlug.trim() } : {})
      },
      {
        onSuccess: (collective) => {
          void navigate(`/c/${collective.slug}/admin`);
        }
      }
    );
  };

  const canContinue = step !== 1 || name.trim().length > 0;

  return (
    <div className='mx-auto max-w-3xl px-6 py-8'>
      <div className='mb-8'>
        <Button
          asChild
          variant='ghost'
          size='sm'
          className='text-muted-foreground hover:text-foreground mb-4 -ml-2'
        >
          <Link to='/collectives'>
            <ArrowLeft className='mr-2 h-4 w-4' />
            Back to Collectives
          </Link>
        </Button>
        <h1 className='font-rubik text-foreground text-3xl font-semibold'>Create a Collective</h1>
        <p className='font-inter text-muted-foreground mt-1'>
          Group endpoints under one identity data buyers can discover and trust
        </p>
      </div>

      <div className='mb-8 flex items-center justify-between'>
        {STEPS.map((s, index) => {
          const Icon = s.icon;
          const isActive = s.id === step;
          const isDone = s.id < step;
          return (
            <div key={s.id} className='flex flex-1 items-center'>
              <div className='flex items-center'>
                <div
                  className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-full',
                    isActive && 'bg-primary text-primary-foreground',
                    isDone && 'bg-primary/20 text-primary',
                    !isActive && !isDone && 'bg-muted text-muted-foreground'
                  )}
                >
                  {isDone ? <Check className='h-5 w-5' /> : <Icon className='h-5 w-5' />}
                </div>
                <span
                  className={cn(
                    'ml-3 text-sm font-medium',
                    isActive ? 'text-foreground' : 'text-muted-foreground'
                  )}
                >
                  {s.name}
                </span>
              </div>
              {index < STEPS.length - 1 && (
                <div className={cn('mx-4 h-0.5 flex-1', isDone ? 'bg-primary/20' : 'bg-muted')} />
              )}
            </div>
          );
        })}
      </div>

      <Card className='p-6'>
        {step === 1 && (
          <div className='space-y-6'>
            <h2 className='text-lg font-semibold'>Details</h2>
            <div>
              <Label htmlFor='name'>Collective name *</Label>
              <Input
                id='name'
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                }}
                placeholder='e.g. Genomics Research Collective'
                className='mt-1'
              />
            </div>
            <div>
              <Label htmlFor='slug'>URL slug</Label>
              <Input
                id='slug'
                value={slugPreview}
                onChange={(e) => {
                  setCustomSlug(e.target.value);
                }}
                placeholder='auto-generated from the name'
                className='mt-1 font-mono text-sm'
              />
              <p className='text-muted-foreground mt-1 text-xs'>
                Your collective will live at /c/{slugPreview || '...'}
              </p>
            </div>
            <div>
              <Label htmlFor='description'>Description</Label>
              <Textarea
                id='description'
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value);
                }}
                placeholder="Describe the collective's focus and the kind of endpoints it groups..."
                rows={3}
                className='mt-1'
              />
              <p className='text-muted-foreground mt-1 text-xs'>
                Short summary shown on cards and the detail header.
              </p>
            </div>
            <div>
              <Label htmlFor='about'>About (optional)</Label>
              <Textarea
                id='about'
                value={about}
                onChange={(e) => {
                  setAbout(e.target.value);
                }}
                placeholder='# About this collective&#10;&#10;Long-form description — supports markdown.'
                rows={10}
                className='mt-1 font-mono text-sm'
              />
              <p className='text-muted-foreground mt-1 text-xs'>
                Long-form markdown, shown as the "About" card on the collective page.
              </p>
            </div>
            <div>
              <Label htmlFor='icon'>Icon URL (optional)</Label>
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
              <Label htmlFor='tags'>Tags (optional)</Label>
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
        )}

        {step === 2 && (
          <div className='space-y-6'>
            <h2 className='text-lg font-semibold'>Membership</h2>
            <p className='text-muted-foreground text-sm'>
              How should endpoints join this collective?
            </p>
            <div className='grid gap-3'>
              {[
                {
                  value: false,
                  title: 'Request to join',
                  body: 'Endpoint owners request membership; you approve each one.'
                },
                {
                  value: true,
                  title: 'Open',
                  body: 'Join requests are approved automatically — anyone can add an endpoint.'
                }
              ].map((option) => (
                <Card
                  key={option.title}
                  className={cn(
                    'cursor-pointer p-4 transition-colors',
                    autoApprove === option.value && 'ring-primary ring-2'
                  )}
                  onClick={() => {
                    setAutoApprove(option.value);
                  }}
                >
                  <div className='flex items-start gap-3'>
                    <div
                      className={cn(
                        'mt-0.5 h-4 w-4 rounded-full border-2',
                        autoApprove === option.value
                          ? 'border-primary bg-primary'
                          : 'border-muted-foreground'
                      )}
                    >
                      {autoApprove === option.value && (
                        <div className='m-0.5 h-2 w-2 rounded-full bg-white' />
                      )}
                    </div>
                    <div>
                      <p className='font-medium'>{option.title}</p>
                      <p className='text-muted-foreground mt-1 text-sm'>{option.body}</p>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        )}

        {step === 3 && (
          <div className='space-y-6'>
            <h2 className='text-lg font-semibold'>Review &amp; create</h2>
            <div className='bg-muted/50 space-y-2 rounded-lg p-4 text-sm'>
              <div className='flex justify-between'>
                <span className='text-muted-foreground'>Name</span>
                <span className='font-medium'>{name.trim() || 'Not set'}</span>
              </div>
              <div className='flex justify-between'>
                <span className='text-muted-foreground'>URL</span>
                <span className='font-mono'>/c/{slugPreview || '...'}</span>
              </div>
              <div className='flex justify-between'>
                <span className='text-muted-foreground'>Membership</span>
                <Badge variant='outline'>{autoApprove ? 'Open' : 'Request to join'}</Badge>
              </div>
              {tags.trim() && (
                <div className='flex justify-between gap-4'>
                  <span className='text-muted-foreground'>Tags</span>
                  <span className='text-right'>{tags}</span>
                </div>
              )}
            </div>
            {createCollective.isError && (
              <p className='text-destructive text-sm'>
                {createCollective.error instanceof Error
                  ? createCollective.error.message
                  : 'Failed to create collective'}
              </p>
            )}
          </div>
        )}
      </Card>

      <div className='mt-6 flex justify-between'>
        {step > 1 ? (
          <Button
            variant='outline'
            onClick={() => {
              setStep(step - 1);
            }}
          >
            <ArrowLeft className='mr-2 h-4 w-4' />
            Back
          </Button>
        ) : (
          <Button asChild variant='outline'>
            <Link to='/collectives'>Cancel</Link>
          </Button>
        )}

        {step < STEPS.length ? (
          <Button
            onClick={() => {
              setStep(step + 1);
            }}
            disabled={!canContinue}
          >
            Next
            <ArrowRight className='ml-2 h-4 w-4' />
          </Button>
        ) : (
          <Button onClick={handleCreate} disabled={createCollective.isPending || !name.trim()}>
            <Check className='mr-2 h-4 w-4' />
            {createCollective.isPending ? 'Creating...' : 'Create collective'}
          </Button>
        )}
      </div>
    </div>
  );
}
