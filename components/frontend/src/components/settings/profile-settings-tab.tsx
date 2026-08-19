import React, { useCallback, useEffect, useState } from 'react';

import type { User as FrontendUser } from '@/lib/types';
import type { AvailabilityState } from './username-field';

import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Mail from 'lucide-react/dist/esm/icons/mail';
import Save from 'lucide-react/dist/esm/icons/save';
import UserIcon from 'lucide-react/dist/esm/icons/user';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useAuth } from '@/context/auth-context';
import {
  checkEmailAvailability,
  checkUsernameAvailability,
  requestEmailChangeAPI,
  updateUserProfileAPI
} from '@/lib/sdk-client';
import { useSettingsModalStore } from '@/stores/settings-modal-store';

import { AvatarSection } from './avatar-section';
import { DisplayNameField } from './display-name-field';
import { PendingEmailCard } from './pending-email-card';
import { StatusMessage } from './status-message';
import { UsernameField } from './username-field';

interface ProfileFormData {
  username: string;
  email: string;
  full_name: string;
  avatar_url: string;
  domain: string;
  bio: string;
  is_email_public: boolean;
}

const BIO_MAX_LENGTH = 2000;

// The backend requires a protocol on `domain`; default to https:// when the
// user typed a bare host, but keep an explicit http:// (local dev) or
// tunneling: prefix. Pasted schemes are lowercased — the backend matches
// them case-sensitively.
function normalizeDomainInput(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return trimmed;
  const scheme = /^(https?:\/\/|tunneling:)/i.exec(trimmed)?.[0];
  if (!scheme) return `https://${trimmed}`;
  return scheme.toLowerCase() + trimmed.slice(scheme.length);
}

/**
 * Collect only the profile fields that actually changed.
 *
 * `email` is deliberately absent: it is not a profile field, and the endpoint
 * rejects it. An email change is dispatched separately by handleSubmit.
 */
function buildProfileUpdates(
  formData: ProfileFormData,
  user: FrontendUser | null
): Record<string, string | boolean> {
  const updates: Record<string, string | boolean> = {};
  if (formData.username !== user?.username) {
    updates.username = formData.username.trim().toLowerCase();
  }
  if (formData.full_name !== user?.full_name) {
    updates.full_name = formData.full_name.trim();
  }
  if (formData.avatar_url !== (user?.avatar_url ?? '')) {
    updates.avatar_url = formData.avatar_url.trim();
  }
  if (formData.domain !== (user?.domain ?? '')) {
    updates.domain = normalizeDomainInput(formData.domain);
  }
  if (formData.bio !== (user?.bio ?? '')) {
    updates.bio = formData.bio;
  }
  if (formData.is_email_public !== (user?.is_email_public ?? false)) {
    updates.is_email_public = formData.is_email_public;
  }
  return updates;
}

export function ProfileSettingsTab() {
  const { user, updateUser, refreshUser } = useAuth();
  const { closeSettings } = useSettingsModalStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [formData, setFormData] = useState<ProfileFormData>({
    username: user?.username ?? '',
    email: user?.email ?? '',
    full_name: user?.full_name ?? '',
    avatar_url: user?.avatar_url ?? '',
    domain: user?.domain ?? '',
    bio: user?.bio ?? '',
    is_email_public: user?.is_email_public ?? false
  });

  // Sync form data when user context changes (e.g., after successful update)
  useEffect(() => {
    if (user) {
      setFormData({
        username: user.username,
        email: user.email,
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- Defensive null check
        full_name: user.full_name ?? '',
        avatar_url: user.avatar_url ?? '',
        domain: user.domain ?? '',
        bio: user.bio ?? '',
        is_email_public: user.is_email_public ?? false
      });
    }
  }, [user]);

  const [usernameAvailability, setUsernameAvailability] = useState<AvailabilityState>({
    checking: false,
    available: null,
    message: null
  });

  const [emailAvailability, setEmailAvailability] = useState<AvailabilityState>({
    checking: false,
    available: null,
    message: null
  });

  // Debounced username availability check
  useEffect(() => {
    const username = formData.username.trim().toLowerCase();

    // Skip if same as current or empty
    if (!username || username === user?.username.toLowerCase()) {
      setUsernameAvailability({ checking: false, available: null, message: null });
      return;
    }

    // Validate username format
    if (!/^[a-z0-9_-]+$/.test(username)) {
      setUsernameAvailability({
        checking: false,
        available: false,
        message: 'Only letters, numbers, underscores, and hyphens allowed'
      });
      return;
    }

    if (username.length < 3) {
      setUsernameAvailability({
        checking: false,
        available: false,
        message: 'Username must be at least 3 characters'
      });
      return;
    }

    setUsernameAvailability({ checking: true, available: null, message: null });

    const timeoutId = setTimeout(() => {
      void (async () => {
        try {
          const result = await checkUsernameAvailability(username);
          setUsernameAvailability({
            checking: false,
            available: result.available,
            message: result.available ? 'Username is available' : 'Username is already taken'
          });
        } catch {
          setUsernameAvailability({
            checking: false,
            available: null,
            message: 'Failed to check availability'
          });
        }
      })();
    }, 500);

    return () => {
      clearTimeout(timeoutId);
    };
  }, [formData.username, user?.username]);

  // Debounced email availability check
  useEffect(() => {
    const email = formData.email.trim().toLowerCase();

    // Skip if same as current or empty
    if (!email || email === user?.email.toLowerCase()) {
      setEmailAvailability({ checking: false, available: null, message: null });
      return;
    }

    // Validate email format (using a ReDoS-safe pattern)
    if (!/^[^\s@]{1,64}@[^\s@]{1,255}$/.test(email) || !email.includes('.')) {
      setEmailAvailability({
        checking: false,
        available: false,
        message: 'Please enter a valid email address'
      });
      return;
    }

    setEmailAvailability({ checking: true, available: null, message: null });

    const timeoutId = setTimeout(() => {
      void (async () => {
        try {
          const result = await checkEmailAvailability(email);
          setEmailAvailability({
            checking: false,
            available: result.available,
            message: result.available ? 'Email is available' : 'Email is already registered'
          });
        } catch {
          setEmailAvailability({
            checking: false,
            available: null,
            message: 'Failed to check availability'
          });
        }
      })();
    }, 500);

    return () => {
      clearTimeout(timeoutId);
    };
  }, [formData.email, user?.email]);

  const handleInputChange = useCallback((field: keyof ProfileFormData) => {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setFormData((previous) => ({ ...previous, [field]: e.target.value }));
      setError(null);
      setSuccess(null);
    };
  }, []);

  const handleBioChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setFormData((previous) => ({ ...previous, bio: e.target.value }));
    setError(null);
    setSuccess(null);
  }, []);

  const handleEmailVisibilityChange = useCallback((checked: boolean) => {
    setFormData((previous) => ({ ...previous, is_email_public: checked }));
    setError(null);
    setSuccess(null);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Validate availability before submitting
    if (usernameAvailability.available === false) {
      setError('Please choose a different username');
      return;
    }
    if (emailAvailability.available === false) {
      setError('Please choose a different email');
      return;
    }

    const updates = buildProfileUpdates(formData, user);

    // An email change is a separate operation against a separate endpoint: it
    // needs proof of the new address, so it cannot ride along with fields that
    // apply immediately.
    const newEmail =
      formData.email.trim().toLowerCase() === (user?.email ?? '').toLowerCase()
        ? null
        : formData.email.trim().toLowerCase();

    // If nothing changed, show message
    if (Object.keys(updates).length === 0 && newEmail === null) {
      setSuccess('No changes to save');
      return;
    }

    setIsLoading(true);

    try {
      if (Object.keys(updates).length > 0) {
        const updatedUser = await updateUserProfileAPI(updates);
        updateUser(updatedUser);
      }

      if (newEmail === null) {
        setSuccess('Profile updated successfully!');
      } else {
        const pending = await requestEmailChangeAPI(newEmail);
        // Re-read so `pending_email` lands in the session and the card appears.
        await refreshUser();
        setSuccess(`Check ${pending} for a code to confirm your new address.`);
      }

      // Clear success message after 3 seconds
      setTimeout(() => {
        setSuccess(null);
      }, 3000);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Failed to update profile');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Fold the outcome of a pending email change back into the session.
   *
   * A confirmed change hands back the updated user; a cancellation returns no
   * body, so the user is re-read to drop the stale `pending_email`.
   */
  const handlePendingEmailResolved = async (updatedUser: FrontendUser | null) => {
    if (updatedUser) {
      updateUser(updatedUser);
      setSuccess(`Your email address is now ${updatedUser.email}.`);
    } else {
      await refreshUser();
      setSuccess('Email change cancelled.');
    }
    setTimeout(() => {
      setSuccess(null);
    }, 3000);
  };

  /* eslint-disable @typescript-eslint/no-unnecessary-condition -- Defensive null checks */
  const hasChanges =
    formData.username !== user?.username ||
    formData.email !== user?.email ||
    formData.full_name !== (user?.full_name ?? '') ||
    formData.avatar_url !== (user?.avatar_url ?? '') ||
    formData.domain !== (user?.domain ?? '') ||
    formData.bio !== (user?.bio ?? '') ||
    formData.is_email_public !== (user?.is_email_public ?? false);
  /* eslint-enable @typescript-eslint/no-unnecessary-condition */

  const canSubmit =
    hasChanges &&
    !isLoading &&
    usernameAvailability.available !== false &&
    emailAvailability.available !== false &&
    !usernameAvailability.checking &&
    !emailAvailability.checking;

  return (
    <div className='space-y-6'>
      <div>
        <h3 className='text-foreground text-lg font-semibold'>Profile Settings</h3>
        <p className='text-muted-foreground mt-1 text-sm'>
          Update your personal information and how others see you on SyftHub.
        </p>
      </div>

      {/* Status Messages */}
      <StatusMessage type='success' message={success} />
      <StatusMessage type='error' message={error} />

      <form onSubmit={handleSubmit} className='space-y-5'>
        {/* Avatar Preview and URL */}
        <AvatarSection
          avatarUrl={formData.avatar_url}
          fullName={formData.full_name}
          onChange={handleInputChange('avatar_url')}
          isLoading={isLoading}
        />

        {/* Username */}
        <UsernameField
          value={formData.username}
          onChange={handleInputChange('username')}
          isLoading={isLoading}
          availability={usernameAvailability}
        />

        {/* Email */}
        <div className='space-y-2'>
          <Label htmlFor='email'>Email</Label>
          <div className='relative'>
            <Input
              id='email'
              type='email'
              value={formData.email}
              onChange={handleInputChange('email')}
              placeholder='you@example.com'
              disabled={isLoading}
              className={(() => {
                if (emailAvailability.available === false) {
                  return 'border-red-300 focus:border-red-500 focus:ring-red-500';
                }
                if (emailAvailability.available === true) {
                  return 'border-green-300 focus:border-green-500 focus:ring-green-500';
                }
                return '';
              })()}
            />
            {emailAvailability.checking ? (
              <div className='absolute top-1/2 right-3 -translate-y-1/2'>
                <Loader2 className='text-muted-foreground h-4 w-4 animate-spin' />
              </div>
            ) : null}
            {!emailAvailability.checking && emailAvailability.available === true ? (
              <div className='absolute top-1/2 right-3 -translate-y-1/2'>
                <Check className='h-4 w-4 text-green-500' />
              </div>
            ) : null}
            {!emailAvailability.checking && emailAvailability.available === false ? (
              <div className='absolute top-1/2 right-3 -translate-y-1/2'>
                <AlertCircle className='h-4 w-4 text-red-500' />
              </div>
            ) : null}
          </div>
          {emailAvailability.message ? (
            <p
              className={`text-xs ${
                emailAvailability.available === false ? 'text-red-600' : 'text-green-600'
              }`}
            >
              {emailAvailability.message}
            </p>
          ) : null}
        </div>

        {/* Email change awaiting verification. Driven by server state, so it is
            here on reload, on a new session, and on another device. */}
        {user?.pending_email ? (
          <PendingEmailCard
            pendingEmail={user.pending_email}
            currentEmail={user.email}
            onResolved={(updatedUser) => void handlePendingEmailResolved(updatedUser)}
          />
        ) : null}

        {/* Full Name */}
        <DisplayNameField
          value={formData.full_name}
          onChange={handleInputChange('full_name')}
          isLoading={isLoading}
        />

        {/* Public Profile Section */}
        <div className='border-border mt-6 border-t pt-6'>
          <div className='mb-4 flex items-center gap-2'>
            <UserIcon className='text-muted-foreground h-4 w-4' />
            <h4 className='text-muted-foreground text-sm font-medium'>Public profile</h4>
          </div>
          <p className='text-muted-foreground mb-4 text-xs'>
            What anonymous viewers see at{' '}
            <span className='font-mono'>/{user?.username ?? 'username'}</span>.
          </p>

          {/* Bio */}
          <div className='space-y-2'>
            <div className='flex items-center justify-between'>
              <Label htmlFor='bio'>Bio</Label>
              <span className='text-muted-foreground text-[11px] tabular-nums'>
                {formData.bio.length}/{BIO_MAX_LENGTH}
              </span>
            </div>
            <textarea
              id='bio'
              value={formData.bio}
              onChange={handleBioChange}
              placeholder='Tell others what you do, what you publish, or what you care about. Markdown is supported.'
              disabled={isLoading}
              rows={5}
              maxLength={BIO_MAX_LENGTH}
              className='font-inter border-border bg-background focus:ring-ring/30 w-full resize-y rounded-md border px-3 py-2 text-sm focus:ring-2 focus:outline-none'
            />
            <p className='text-muted-foreground text-xs'>
              Supports Markdown. Headings, lists, links, and code blocks render on your profile.
            </p>
          </div>

          {/* Email visibility toggle */}
          <div className='border-border mt-5 flex items-start justify-between gap-4 rounded-lg border p-4'>
            <div className='flex items-start gap-3'>
              <Mail
                className='text-muted-foreground mt-0.5 h-4 w-4 flex-shrink-0'
                aria-hidden='true'
              />
              <div>
                <p className='text-foreground text-sm font-medium'>Show email on public profile</p>
                <p className='text-muted-foreground mt-1 text-xs'>
                  When enabled, your email address is visible to anyone viewing your profile page.
                  Off by default.
                </p>
              </div>
            </div>
            <Switch
              checked={formData.is_email_public}
              onCheckedChange={handleEmailVisibilityChange}
              disabled={isLoading}
              aria-label='Show email on public profile'
            />
          </div>
        </div>

        {/* Endpoint Configuration Section */}
        <div className='border-border mt-6 border-t pt-6'>
          <div className='mb-4 flex items-center gap-2'>
            <Globe className='text-muted-foreground h-4 w-4' />
            <h4 className='text-muted-foreground text-sm font-medium'>Endpoint Configuration</h4>
          </div>
          <p className='text-muted-foreground mb-4 text-xs'>
            Configure the domain where your endpoints are hosted. This is used to construct full
            URLs for your endpoints.
          </p>

          {/* Domain */}
          <div className='space-y-2'>
            <Label htmlFor='domain'>API Domain</Label>
            <Input
              id='domain'
              value={formData.domain}
              onChange={handleInputChange('domain')}
              placeholder='api.example.com or api.example.com:8080'
              disabled={isLoading}
            />
            <p className='text-muted-foreground text-xs'>
              Enter the base domain for your endpoints. https:// is assumed unless you include a
              protocol (e.g. http:// for local development).
            </p>
          </div>
        </div>

        {/* Submit Button */}
        <div className='border-border flex justify-end gap-3 border-t pt-4'>
          <Button type='button' variant='outline' onClick={closeSettings} disabled={isLoading}>
            Cancel
          </Button>
          <Button type='submit' disabled={!canSubmit} className='flex items-center gap-2'>
            {isLoading ? (
              <>
                <Loader2 className='h-4 w-4 animate-spin' />
                Saving…
              </>
            ) : (
              <>
                <Save className='h-4 w-4' aria-hidden='true' />
                Save Changes
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
