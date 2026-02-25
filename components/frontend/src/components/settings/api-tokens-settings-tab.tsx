import React, { useCallback, useEffect, useState } from 'react';

import type { APIToken, APITokenCreateResponse, APITokenScope } from '@/lib/sdk-client';

import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';
import Clock from 'lucide-react/dist/esm/icons/clock';
import Copy from 'lucide-react/dist/esm/icons/copy';
import Key from 'lucide-react/dist/esm/icons/key';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Pencil from 'lucide-react/dist/esm/icons/pencil';
import Plus from 'lucide-react/dist/esm/icons/plus';
import Shield from 'lucide-react/dist/esm/icons/shield';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';
import X from 'lucide-react/dist/esm/icons/x';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { syftClient } from '@/lib/sdk-client';
import { cn } from '@/lib/utils';

import { StatusMessage } from './status-message';

// Constants
const MAX_TOKENS_PER_USER = 50;

// Helper functions
function formatDate(date: Date | string): string {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
}

function formatRelativeTime(date: Date | string): string {
  const now = new Date();
  const then = new Date(date);
  const diffMs = now.getTime() - then.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${String(diffMins)} minute${diffMins === 1 ? '' : 's'} ago`;
  if (diffHours < 24) return `${String(diffHours)} hour${diffHours === 1 ? '' : 's'} ago`;
  if (diffDays < 30) return `${String(diffDays)} day${diffDays === 1 ? '' : 's'} ago`;
  return formatDate(date);
}

function getExpirationDate(expiration: string, customDate: string): Date | null {
  if (expiration === 'none') return null;
  if (expiration === 'custom' && customDate) return new Date(customDate);

  const now = new Date();
  switch (expiration) {
    case '30d': {
      return new Date(now.getTime() + 30 * 86_400_000);
    }
    case '60d': {
      return new Date(now.getTime() + 60 * 86_400_000);
    }
    case '90d': {
      return new Date(now.getTime() + 90 * 86_400_000);
    }
    case '1y': {
      return new Date(now.getTime() + 365 * 86_400_000);
    }
    default: {
      return null;
    }
  }
}

// Fix #3: Added dark: variants to all scope badge color classes
function getScopeBadgeClass(scope: APITokenScope): string {
  switch (scope) {
    case 'full': {
      return 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900 dark:text-blue-300 dark:border-blue-700';
    }
    case 'write': {
      return 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900 dark:text-amber-300 dark:border-amber-700';
    }
    case 'read': {
      return 'bg-green-100 text-green-700 border-green-200 dark:bg-green-900 dark:text-green-300 dark:border-green-700';
    }
    default: {
      return '';
    }
  }
}

function isTokenExpired(token: APIToken): boolean {
  if (!token.expiresAt) return false;
  return new Date(token.expiresAt).getTime() < Date.now();
}

// Form data types
interface CreateTokenFormData {
  name: string;
  scope: APITokenScope;
  expiration: 'none' | '30d' | '60d' | '90d' | '1y' | 'custom';
  customDate: string;
}

const initialFormData: CreateTokenFormData = {
  name: '',
  scope: 'full',
  expiration: 'none',
  customDate: ''
};

// Scope Badge Component
function ScopeBadge({ scope }: Readonly<{ scope: APITokenScope }>) {
  return (
    <Badge variant='outline' className={cn('text-xs', getScopeBadgeClass(scope))}>
      {scope}
    </Badge>
  );
}

// Token Row Component
interface TokenRowProps {
  token: APIToken;
  onEdit: (token: APIToken) => void;
  onRevoke: (token: APIToken) => void;
}

function TokenRow({ token, onEdit, onRevoke }: Readonly<TokenRowProps>) {
  const expired = isTokenExpired(token);

  return (
    // Fix #8: Removed blunt opacity-60; expired state now uses bg-muted/50 and muted token name
    <div
      className={cn(
        'rounded-lg border p-4 transition-colors',
        expired ? 'border-border bg-muted/50' : 'border-border bg-card'
      )}
    >
      <div className='flex items-start justify-between gap-4'>
        <div className='min-w-0 flex-1'>
          <div className='flex items-center gap-2'>
            <Key className='text-muted-foreground h-4 w-4 shrink-0' aria-hidden='true' />
            <span
              className={cn(
                'truncate font-medium',
                expired ? 'text-muted-foreground' : 'text-foreground'
              )}
            >
              {token.name}
            </span>
            {token.scopes.map((scope: APITokenScope) => (
              <ScopeBadge key={scope} scope={scope} />
            ))}
            {expired ? (
              // Fix #1: Added dark: variants
              <Badge
                variant='outline'
                className='border-red-200 bg-red-50 text-xs text-red-600 dark:border-red-800 dark:bg-red-950 dark:text-red-400'
              >
                Expired
              </Badge>
            ) : null}
            {token.isActive ? null : (
              // Fix #1: Added dark: variants
              <Badge
                variant='outline'
                className='border-gray-200 bg-gray-50 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400'
              >
                Revoked
              </Badge>
            )}
          </div>
          <div className='text-muted-foreground mt-1 font-mono text-xs'>{token.tokenPrefix}...</div>
          <div className='text-muted-foreground mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs'>
            <span>
              {token.lastUsedAt
                ? `Last used: ${formatRelativeTime(token.lastUsedAt)}`
                : 'Never used'}
            </span>
            <span>·</span>
            <span>Created: {formatDate(token.createdAt)}</span>
            {token.expiresAt ? (
              <>
                <span>·</span>
                <span className={expired ? 'text-red-600 dark:text-red-400' : ''}>
                  {expired ? 'Expired' : 'Expires'}: {formatDate(token.expiresAt)}
                </span>
              </>
            ) : null}
          </div>
        </div>
        {token.isActive ? (
          <div className='flex shrink-0 gap-2'>
            <Button
              variant='outline'
              size='sm'
              onClick={() => {
                onEdit(token);
              }}
              className='h-8'
            >
              <Pencil className='mr-1 h-3 w-3' aria-hidden='true' />
              Edit
            </Button>
            <Button
              variant='outline'
              size='sm'
              onClick={() => {
                onRevoke(token);
              }}
              // Fix #1: Added dark: variants to destructive outline button
              className='h-8 border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950 dark:hover:text-red-300'
            >
              <Trash2 className='mr-1 h-3 w-3' aria-hidden='true' />
              Revoke
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

// Empty State Component
function EmptyState({ onCreateClick }: Readonly<{ onCreateClick: () => void }>) {
  return (
    <div className='flex flex-col items-center justify-center rounded-lg border border-dashed py-12'>
      <Key className='text-muted-foreground mb-4 h-12 w-12' aria-hidden='true' />
      <h4 className='text-foreground mb-1 font-medium'>No API tokens yet</h4>
      <p className='text-muted-foreground mb-4 text-sm'>
        Create your first token to access the API programmatically.
      </p>
      <Button onClick={onCreateClick}>
        <Plus className='mr-2 h-4 w-4' aria-hidden='true' />
        Create Token
      </Button>
    </div>
  );
}

// Create Token Modal Component
interface CreateTokenModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (response: APITokenCreateResponse) => void;
}

function CreateTokenModal({ isOpen, onClose, onSuccess }: Readonly<CreateTokenModalProps>) {
  const [formData, setFormData] = useState<CreateTokenFormData>(initialFormData);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleInputChange = useCallback((field: keyof CreateTokenFormData, value: string) => {
    setFormData((previous) => ({ ...previous, [field]: value }));
    setError(null);
  }, []);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    if (!formData.name.trim()) {
      setError('Token name is required');
      return;
    }

    if (formData.name.length > 100) {
      setError('Token name must be 100 characters or less');
      return;
    }

    if (formData.expiration === 'custom' && !formData.customDate) {
      setError('Please select an expiration date');
      return;
    }

    setIsLoading(true);

    try {
      const expiresAt = getExpirationDate(formData.expiration, formData.customDate);
      const response = await syftClient.apiTokens.create({
        name: formData.name.trim(),
        scopes: [formData.scope],
        expiresAt
      });
      onSuccess(response);
      setFormData(initialFormData);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Failed to create token');
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = useCallback(() => {
    setFormData(initialFormData);
    setError(null);
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  return (
    <div className='fixed inset-0 z-[60] flex items-center justify-center p-4'>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className='absolute inset-0 bg-black/50 backdrop-blur-sm'
        onClick={handleClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: 'spring', duration: 0.3 }}
        className='border-border bg-card relative w-full max-w-md rounded-xl border p-6 shadow-xl'
      >
        <div className='mb-4 flex items-center justify-between'>
          <h3 className='text-foreground text-lg font-semibold'>Create New API Token</h3>
          <Button
            variant='ghost'
            size='icon'
            onClick={handleClose}
            className='h-8 w-8'
            aria-label='Close'
          >
            <X className='h-4 w-4' aria-hidden='true' />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className='space-y-4'>
          {/* Fix #2: Replaced custom inline error div with StatusMessage (adds role/aria-live) */}
          <StatusMessage type='error' message={error} />

          <div className='space-y-2'>
            <Label htmlFor='token-name'>Token Name</Label>
            <Input
              id='token-name'
              value={formData.name}
              onChange={(event) => {
                handleInputChange('name', event.target.value);
              }}
              placeholder='e.g., CI/CD Pipeline'
              disabled={isLoading}
              maxLength={100}
            />
            <p className='text-muted-foreground text-xs'>
              A descriptive name to identify this token
            </p>
          </div>

          <div className='space-y-2'>
            <Label>Scopes</Label>
            <div className='space-y-2'>
              {(['full', 'write', 'read'] as const).map((scope) => (
                <label
                  key={scope}
                  className={cn(
                    'flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors',
                    // Fix #7: Use design tokens instead of hardcoded blue
                    formData.scope === scope
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:bg-muted'
                  )}
                >
                  <input
                    type='radio'
                    name='scope'
                    value={scope}
                    checked={formData.scope === scope}
                    onChange={(event) => {
                      handleInputChange('scope', event.target.value);
                    }}
                    className='text-primary h-4 w-4'
                    disabled={isLoading}
                  />
                  <div>
                    <span className='text-foreground font-medium capitalize'>{scope}</span>
                    <p className='text-muted-foreground text-xs'>
                      {scope === 'full' && 'Complete access (recommended)'}
                      {scope === 'write' && 'Create and modify resources'}
                      {scope === 'read' && 'Read-only access'}
                    </p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className='space-y-2'>
            <Label htmlFor='expiration'>Expiration</Label>
            {/* Fix #6: Replace raw <select> with shared Select UI component */}
            <Select
              value={formData.expiration}
              onValueChange={(value) => {
                handleInputChange('expiration', value);
              }}
              disabled={isLoading}
            >
              <SelectTrigger id='expiration'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='none'>No expiration</SelectItem>
                <SelectItem value='30d'>30 days</SelectItem>
                <SelectItem value='60d'>60 days</SelectItem>
                <SelectItem value='90d'>90 days</SelectItem>
                <SelectItem value='1y'>1 year</SelectItem>
                <SelectItem value='custom'>Custom date</SelectItem>
              </SelectContent>
            </Select>
            {formData.expiration === 'custom' ? (
              <Input
                type='date'
                value={formData.customDate}
                onChange={(event) => {
                  handleInputChange('customDate', event.target.value);
                }}
                min={new Date().toISOString().split('T')[0]}
                disabled={isLoading}
              />
            ) : null}
          </div>

          <div className='flex justify-end gap-3 pt-2'>
            <Button type='button' variant='outline' onClick={handleClose} disabled={isLoading}>
              Cancel
            </Button>
            <Button type='submit' disabled={isLoading || !formData.name.trim()}>
              {isLoading ? (
                <>
                  <Loader2 className='mr-2 h-4 w-4 animate-spin' aria-hidden='true' />
                  Creating...
                </>
              ) : (
                <>
                  <Plus className='mr-2 h-4 w-4' aria-hidden='true' />
                  Create Token
                </>
              )}
            </Button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}

// Token Created Success Modal Component
interface TokenCreatedModalProps {
  token: APITokenCreateResponse | null;
  onClose: () => void;
}

function TokenCreatedModal({ token, onClose }: Readonly<TokenCreatedModalProps>) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token.token);
      setCopied(true);
      // Fix #12: Increased copy feedback duration from 2s to 3s
      setTimeout(() => {
        setCopied(false);
      }, 3000);
    } catch {
      // Fallback for older browsers that don't support Clipboard API
      const textArea = document.createElement('textarea');
      textArea.value = token.token;
      document.body.append(textArea);
      textArea.select();
      // eslint-disable-next-line sonarjs/deprecation, @typescript-eslint/no-deprecated
      document.execCommand('copy');
      textArea.remove();
      setCopied(true);
      // Fix #12: Increased copy feedback duration from 2s to 3s
      setTimeout(() => {
        setCopied(false);
      }, 3000);
    }
  };

  if (!token) return null;

  return (
    <div className='fixed inset-0 z-[60] flex items-center justify-center p-4'>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className='absolute inset-0 bg-black/50 backdrop-blur-sm'
        // Fix #5: Added backdrop click dismiss
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: 'spring', duration: 0.3 }}
        className='border-border bg-card relative w-full max-w-lg rounded-xl border p-6 shadow-xl'
      >
        <div className='mb-4 flex items-center gap-3'>
          {/* Fix #1: Added dark: variant to success icon bg */}
          <div className='flex h-10 w-10 items-center justify-center rounded-full bg-green-100 dark:bg-green-900'>
            <Check className='h-5 w-5 text-green-600 dark:text-green-400' aria-hidden='true' />
          </div>
          <h3 className='text-foreground text-lg font-semibold'>Token Created Successfully</h3>
        </div>

        {/* Fix #11: Token display moved above warning for better information priority */}
        <div className='mb-4'>
          <Label className='mb-2 block'>Your new API token:</Label>
          <div className='flex items-center gap-2'>
            <div className='bg-muted flex-1 overflow-hidden rounded-lg border p-3'>
              <code className='block truncate font-mono text-sm'>{token.token}</code>
            </div>
            <Button
              variant='outline'
              size='icon'
              onClick={handleCopy}
              className={cn(
                'h-10 w-10 shrink-0',
                copied &&
                  'border-green-500 text-green-600 dark:border-green-600 dark:text-green-400'
              )}
              aria-label={copied ? 'Copied!' : 'Copy token'}
            >
              {copied ? (
                <Check className='h-4 w-4' aria-hidden='true' />
              ) : (
                <Copy className='h-4 w-4' aria-hidden='true' />
              )}
            </Button>
          </div>
        </div>

        {/* Fix #1 + #11: Warning now below token display; added dark: variants */}
        <div className='mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950'>
          <div className='flex items-start gap-2'>
            <AlertCircle
              className='mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400'
              aria-hidden='true'
            />
            <p className='text-sm text-amber-800 dark:text-amber-200'>
              <strong>Make sure to copy your token now!</strong> You won't be able to see it again.
            </p>
          </div>
        </div>

        <div className='text-muted-foreground mb-6 space-y-1 text-sm'>
          <p>
            <strong>Token name:</strong> {token.name}
          </p>
          <p>
            <strong>Scopes:</strong> {token.scopes.join(', ')}
          </p>
          <p>
            <strong>Expires:</strong> {token.expiresAt ? formatDate(token.expiresAt) : 'Never'}
          </p>
        </div>

        <div className='flex justify-end'>
          <Button onClick={onClose}>Done</Button>
        </div>
      </motion.div>
    </div>
  );
}

// Edit Token Modal Component
interface EditTokenModalProps {
  token: APIToken | null;
  onClose: () => void;
  onSuccess: (updated: APIToken) => void;
}

function EditTokenModal({ token, onClose, onSuccess }: Readonly<EditTokenModalProps>) {
  const [name, setName] = useState(token?.name ?? '');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) {
      setName(token.name);
    }
  }, [token]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!token) return;

    setError(null);

    if (!name.trim()) {
      setError('Token name is required');
      return;
    }

    if (name.length > 100) {
      setError('Token name must be 100 characters or less');
      return;
    }

    setIsLoading(true);

    try {
      const updated = await syftClient.apiTokens.update(token.id, { name: name.trim() });
      onSuccess(updated);
      onClose();
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Failed to update token');
    } finally {
      setIsLoading(false);
    }
  };

  if (!token) return null;

  return (
    <div className='fixed inset-0 z-[60] flex items-center justify-center p-4'>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className='absolute inset-0 bg-black/50 backdrop-blur-sm'
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: 'spring', duration: 0.3 }}
        className='border-border bg-card relative w-full max-w-md rounded-xl border p-6 shadow-xl'
      >
        <div className='mb-4 flex items-center justify-between'>
          <h3 className='text-foreground text-lg font-semibold'>Edit Token</h3>
          <Button
            variant='ghost'
            size='icon'
            onClick={onClose}
            className='h-8 w-8'
            aria-label='Close'
          >
            <X className='h-4 w-4' aria-hidden='true' />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className='space-y-4'>
          {/* Fix #2: Replaced custom inline error div with StatusMessage (adds role/aria-live) */}
          <StatusMessage type='error' message={error} />

          <div className='space-y-2'>
            <Label htmlFor='edit-token-name'>Token Name</Label>
            <Input
              id='edit-token-name'
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setError(null);
              }}
              placeholder='e.g., CI/CD Pipeline'
              disabled={isLoading}
              maxLength={100}
            />
          </div>

          <div className='flex justify-end gap-3 pt-2'>
            <Button type='button' variant='outline' onClick={onClose} disabled={isLoading}>
              Cancel
            </Button>
            <Button type='submit' disabled={isLoading || !name.trim()}>
              {isLoading ? (
                <>
                  <Loader2 className='mr-2 h-4 w-4 animate-spin' aria-hidden='true' />
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </Button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}

// Revoke Token Confirmation Modal
interface RevokeTokenModalProps {
  token: APIToken | null;
  onClose: () => void;
  onConfirm: () => void;
  isLoading: boolean;
}

function RevokeTokenModal({
  token,
  onClose,
  onConfirm,
  isLoading
}: Readonly<RevokeTokenModalProps>) {
  if (!token) return null;

  return (
    <div className='fixed inset-0 z-[60] flex items-center justify-center p-4'>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className='absolute inset-0 bg-black/50 backdrop-blur-sm'
        onClick={isLoading ? undefined : onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: 'spring', duration: 0.3 }}
        className='border-border bg-card relative w-full max-w-md rounded-xl border p-6 shadow-xl'
      >
        <div className='mb-4 flex items-center gap-3'>
          {/* Fix #1: Added dark: variant to destructive icon bg */}
          <div className='flex h-10 w-10 items-center justify-center rounded-full bg-red-100 dark:bg-red-900'>
            <Trash2 className='h-5 w-5 text-red-600 dark:text-red-400' aria-hidden='true' />
          </div>
          <h3 className='text-foreground text-lg font-semibold'>Revoke Token</h3>
        </div>

        <p className='text-muted-foreground mb-2'>
          Are you sure you want to revoke <strong className='text-foreground'>{token.name}</strong>?
        </p>
        <p className='text-muted-foreground mb-6 text-sm'>
          This action cannot be undone. Any applications using this token will lose access
          immediately.
        </p>

        <div className='flex justify-end gap-3'>
          <Button type='button' variant='outline' onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            type='button'
            variant='destructive'
            onClick={onConfirm}
            disabled={isLoading}
            className='bg-red-600 hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600'
          >
            {isLoading ? (
              <>
                <Loader2 className='mr-2 h-4 w-4 animate-spin' aria-hidden='true' />
                Revoking...
              </>
            ) : (
              <>
                <Trash2 className='mr-2 h-4 w-4' aria-hidden='true' />
                Revoke Token
              </>
            )}
          </Button>
        </div>
      </motion.div>
    </div>
  );
}

// Main Component
export function APITokensSettingsTab() {
  const [tokens, setTokens] = useState<APIToken[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createdToken, setCreatedToken] = useState<APITokenCreateResponse | null>(null);
  const [editingToken, setEditingToken] = useState<APIToken | null>(null);
  const [tokenToRevoke, setTokenToRevoke] = useState<APIToken | null>(null);
  const [isRevoking, setIsRevoking] = useState(false);

  const fetchTokens = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await syftClient.apiTokens.list();
      setTokens(response.tokens);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Failed to load tokens');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchTokens();
  }, [fetchTokens]);

  const handleCreateSuccess = useCallback((response: APITokenCreateResponse) => {
    setShowCreateModal(false);
    setCreatedToken(response);
    // Add the new token to the list (without the actual token value)
    // eslint-disable-next-line @typescript-eslint/no-unused-vars, sonarjs/no-unused-vars
    const { token: _unusedToken, ...tokenWithoutValue } = response;
    setTokens((previous) => [tokenWithoutValue as APIToken, ...previous]);
  }, []);

  const handleEditSuccess = useCallback((updated: APIToken) => {
    setTokens((previous) => previous.map((t) => (t.id === updated.id ? updated : t)));
    setEditingToken(null);
  }, []);

  const handleRevoke = useCallback(async () => {
    if (!tokenToRevoke) return;

    setIsRevoking(true);

    try {
      await syftClient.apiTokens.revoke(tokenToRevoke.id);
      setTokens((previous) => previous.filter((t) => t.id !== tokenToRevoke.id));
      setTokenToRevoke(null);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Failed to revoke token');
    } finally {
      setIsRevoking(false);
    }
  }, [tokenToRevoke]);

  const handleCloseCreatedModal = useCallback(() => {
    setCreatedToken(null);
  }, []);

  const atMaxTokens = tokens.length >= MAX_TOKENS_PER_USER;

  return (
    <div className='space-y-6'>
      {/* Header */}
      <div>
        <h3 className='text-foreground text-lg font-semibold'>API Tokens</h3>
        <p className='text-muted-foreground mt-1 text-sm'>
          Create and manage personal access tokens for API access.
        </p>
      </div>

      {/* Fix #1: Info Banner — added dark: variants */}
      <div className='rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950'>
        <div className='flex items-start gap-3'>
          <Shield className='mt-0.5 h-5 w-5 text-blue-600 dark:text-blue-400' aria-hidden='true' />
          <div>
            <h4 className='text-sm font-medium text-blue-900 dark:text-blue-100'>
              Personal Access Tokens
            </h4>
            <p className='mt-1 text-xs text-blue-700 dark:text-blue-300'>
              Tokens provide secure API access without sharing your password. Keep them secret and
              revoke any tokens you no longer need.
            </p>
          </div>
        </div>
      </div>

      {/* Fix #4: Replaced custom inline error with StatusMessage + action prop */}
      <StatusMessage
        type='error'
        message={error}
        action={{
          label: 'Retry',
          onClick: () => {
            void fetchTokens();
          }
        }}
      />

      {/* Create Token Button */}
      <div className='border-border flex items-center justify-between border-b pb-3'>
        <div className='flex items-center gap-2'>
          <Key className='text-muted-foreground h-4 w-4' aria-hidden='true' />
          <h4 className='text-foreground font-medium'>Your Tokens</h4>
          {/* Fix #9: Token counter as Badge instead of plain parenthesized text */}
          <Badge variant='outline' className='text-xs'>
            {tokens.length}/{MAX_TOKENS_PER_USER}
          </Badge>
        </div>
        <Button
          onClick={() => {
            setShowCreateModal(true);
          }}
          disabled={isLoading || atMaxTokens}
          size='sm'
        >
          <Plus className='mr-2 h-4 w-4' aria-hidden='true' />
          Create Token
        </Button>
      </div>

      {/* Fix #1: Max Tokens Warning — added dark: variants */}
      {atMaxTokens ? (
        <div className='flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950'>
          <Clock className='h-4 w-4 text-amber-600 dark:text-amber-400' aria-hidden='true' />
          <span className='text-sm text-amber-800 dark:text-amber-200'>
            You've reached the maximum of {MAX_TOKENS_PER_USER} tokens. Revoke unused tokens to
            create new ones.
          </span>
        </div>
      ) : null}

      {/* Fix #10: Aligned loading spinner padding to py-8 (matches Aggregator tab) */}
      {isLoading ? (
        <div className='flex items-center justify-center py-8'>
          <Loader2 className='text-muted-foreground h-8 w-8 animate-spin' aria-hidden='true' />
        </div>
      ) : null}

      {!isLoading && tokens.length === 0 ? (
        <EmptyState
          onCreateClick={() => {
            setShowCreateModal(true);
          }}
        />
      ) : null}

      {!isLoading && tokens.length > 0 ? (
        <div className='space-y-3'>
          {tokens.map((token) => (
            <TokenRow
              key={token.id}
              token={token}
              onEdit={setEditingToken}
              onRevoke={setTokenToRevoke}
            />
          ))}
        </div>
      ) : null}

      {/* Modals */}
      <AnimatePresence>
        {showCreateModal ? (
          <CreateTokenModal
            isOpen={showCreateModal}
            onClose={() => {
              setShowCreateModal(false);
            }}
            onSuccess={handleCreateSuccess}
          />
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {createdToken ? (
          <TokenCreatedModal token={createdToken} onClose={handleCloseCreatedModal} />
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {editingToken ? (
          <EditTokenModal
            token={editingToken}
            onClose={() => {
              setEditingToken(null);
            }}
            onSuccess={handleEditSuccess}
          />
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {tokenToRevoke ? (
          <RevokeTokenModal
            token={tokenToRevoke}
            onClose={() => {
              setTokenToRevoke(null);
            }}
            onConfirm={handleRevoke}
            isLoading={isRevoking}
          />
        ) : null}
      </AnimatePresence>
    </div>
  );
}
