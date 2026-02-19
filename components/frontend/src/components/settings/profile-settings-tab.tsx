import React, { useCallback, useEffect, useState } from 'react';

import type { AvailabilityState } from './username-field';

import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Save from 'lucide-react/dist/esm/icons/save';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/context/auth-context';
import {
  checkEmailAvailability,
  checkUsernameAvailability,
  updateUserProfileAPI
} from '@/lib/sdk-client';
import { useSettingsModalStore } from '@/stores/settings-modal-store';

import { AvatarSection } from './avatar-section';
import { DisplayNameField } from './display-name-field';
import { StatusMessage } from './status-message';
import { UsernameField } from './username-field';

interface ProfileFormData {
  username: string;
  email: string;
  full_name: string;
  avatar_url: string;
  domain: string;
}

export function ProfileSettingsTab() {
  const { user, updateUser } = useAuth();
  const { closeSettings } = useSettingsModalStore();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [formData, setFormData] = useState<ProfileFormData>({
    username: user?.username ?? '',
    email: user?.email ?? '',
    full_name: user?.full_name ?? '',
    avatar_url: user?.avatar_url ?? '',
    domain: user?.domain ?? ''
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
        domain: user.domain ?? ''
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

    // Build update payload (only changed fields)
    const updates: Record<string, string> = {};
    if (formData.username !== user?.username) {
      updates.username = formData.username.trim().toLowerCase();
    }
    if (formData.email !== user?.email) {
      updates.email = formData.email.trim().toLowerCase();
    }
    if (formData.full_name !== user?.full_name) {
      updates.full_name = formData.full_name.trim();
    }
    if (formData.avatar_url !== (user?.avatar_url ?? '')) {
      updates.avatar_url = formData.avatar_url.trim();
    }
    if (formData.domain !== (user?.domain ?? '')) {
      // Strip protocol if user accidentally included it
      let domainValue = formData.domain.trim();
      domainValue = domainValue.replace(/^https?:\/\//, '');
      updates.domain = domainValue;
    }

    // If nothing changed, show message
    if (Object.keys(updates).length === 0) {
      setSuccess('No changes to save');
      return;
    }

    setIsLoading(true);

    try {
      // Update profile and get the updated user directly from the response
      const updatedUser = await updateUserProfileAPI(updates);

      // Update auth context directly with the response data (no need for separate API call)
      updateUser(updatedUser);

      setSuccess('Profile updated successfully!');

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

  /* eslint-disable @typescript-eslint/no-unnecessary-condition -- Defensive null checks */
  const hasChanges =
    formData.username !== user?.username ||
    formData.email !== user?.email ||
    formData.full_name !== (user?.full_name ?? '') ||
    formData.avatar_url !== (user?.avatar_url ?? '') ||
    formData.domain !== (user?.domain ?? '');
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

        {/* Full Name */}
        <DisplayNameField
          value={formData.full_name}
          onChange={handleInputChange('full_name')}
          isLoading={isLoading}
        />

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
              Enter the base domain for your endpoints without the protocol (https:// will be added
              automatically).
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
