import React, { useCallback, useEffect, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import { AlertCircle, Check, Globe, Loader2, Save, User } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/context/auth-context';
import { useSettingsModal } from '@/context/settings-modal-context';
import {
  checkEmailAvailability,
  checkUsernameAvailability,
  updateUserProfileAPI
} from '@/lib/sdk-client';

interface ProfileFormData {
  username: string;
  email: string;
  full_name: string;
  avatar_url: string;
  domain: string;
}

interface AvailabilityState {
  checking: boolean;
  available: boolean | null;
  message: string | null;
}

export function ProfileSettingsTab() {
  const { user, updateUser } = useAuth();
  const { closeSettings } = useSettingsModal();
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

  // Generate avatar preview URL
  const avatarPreviewUrl =
    formData.avatar_url ||
    `https://ui-avatars.com/api/?name=${encodeURIComponent(formData.full_name || 'User')}&background=272532&color=fff`;

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
        <h3 className='text-lg font-semibold text-gray-900'>Profile Settings</h3>
        <p className='mt-1 text-sm text-gray-500'>
          Update your personal information and how others see you on SyftHub.
        </p>
      </div>

      {/* Status Messages */}
      <AnimatePresence>
        {success && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3'
          >
            <Check className='h-4 w-4 text-green-600' />
            <span className='text-sm text-green-800'>{success}</span>
          </motion.div>
        )}

        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className='flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3'
          >
            <AlertCircle className='h-4 w-4 text-red-600' />
            <span className='text-sm text-red-800'>{error}</span>
          </motion.div>
        )}
      </AnimatePresence>

      <form onSubmit={handleSubmit} className='space-y-5'>
        {/* Avatar Preview and URL */}
        <div className='space-y-3'>
          <Label>Profile Picture</Label>
          <div className='flex items-start gap-4'>
            <div className='flex h-16 w-16 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-blue-500 to-purple-600'>
              {avatarPreviewUrl ? (
                <img
                  src={avatarPreviewUrl}
                  alt='Avatar preview'
                  width={64}
                  height={64}
                  loading='lazy'
                  className='h-16 w-16 rounded-full object-cover'
                  onError={(e) => {
                    (e.target as HTMLImageElement).src =
                      `https://ui-avatars.com/api/?name=${encodeURIComponent(formData.full_name || 'User')}&background=272532&color=fff`;
                  }}
                />
              ) : (
                <User className='h-8 w-8 text-white' aria-hidden='true' />
              )}
            </div>
            <div className='flex-1'>
              <Input
                type='url'
                value={formData.avatar_url}
                onChange={handleInputChange('avatar_url')}
                placeholder='https://example.com/your-avatar.png'
                disabled={isLoading}
              />
              <p className='mt-1 text-xs text-gray-500'>
                Enter a URL to your profile picture. Leave blank to use an auto-generated avatar.
              </p>
            </div>
          </div>
        </div>

        {/* Username */}
        <div className='space-y-2'>
          <Label htmlFor='username'>Username</Label>
          <div className='relative'>
            <Input
              id='username'
              value={formData.username}
              onChange={handleInputChange('username')}
              placeholder='your-username'
              disabled={isLoading}
              className={(() => {
                if (usernameAvailability.available === false) {
                  return 'border-red-300 focus:border-red-500 focus:ring-red-500';
                }
                if (usernameAvailability.available === true) {
                  return 'border-green-300 focus:border-green-500 focus:ring-green-500';
                }
                return '';
              })()}
            />
            {usernameAvailability.checking && (
              <div className='absolute top-1/2 right-3 -translate-y-1/2'>
                <Loader2 className='h-4 w-4 animate-spin text-gray-400' />
              </div>
            )}
            {!usernameAvailability.checking && usernameAvailability.available === true && (
              <div className='absolute top-1/2 right-3 -translate-y-1/2'>
                <Check className='h-4 w-4 text-green-500' />
              </div>
            )}
            {!usernameAvailability.checking && usernameAvailability.available === false && (
              <div className='absolute top-1/2 right-3 -translate-y-1/2'>
                <AlertCircle className='h-4 w-4 text-red-500' />
              </div>
            )}
          </div>
          {usernameAvailability.message && (
            <p
              className={`text-xs ${
                usernameAvailability.available === false ? 'text-red-600' : 'text-green-600'
              }`}
            >
              {usernameAvailability.message}
            </p>
          )}
        </div>

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
            {emailAvailability.checking && (
              <div className='absolute top-1/2 right-3 -translate-y-1/2'>
                <Loader2 className='h-4 w-4 animate-spin text-gray-400' />
              </div>
            )}
            {!emailAvailability.checking && emailAvailability.available === true && (
              <div className='absolute top-1/2 right-3 -translate-y-1/2'>
                <Check className='h-4 w-4 text-green-500' />
              </div>
            )}
            {!emailAvailability.checking && emailAvailability.available === false && (
              <div className='absolute top-1/2 right-3 -translate-y-1/2'>
                <AlertCircle className='h-4 w-4 text-red-500' />
              </div>
            )}
          </div>
          {emailAvailability.message && (
            <p
              className={`text-xs ${
                emailAvailability.available === false ? 'text-red-600' : 'text-green-600'
              }`}
            >
              {emailAvailability.message}
            </p>
          )}
        </div>

        {/* Full Name */}
        <div className='space-y-2'>
          <Label htmlFor='full_name'>Full Name</Label>
          <Input
            id='full_name'
            value={formData.full_name}
            onChange={handleInputChange('full_name')}
            placeholder='Your full name'
            disabled={isLoading}
          />
        </div>

        {/* Endpoint Configuration Section */}
        <div className='mt-6 border-t border-gray-200 pt-6'>
          <div className='mb-4 flex items-center gap-2'>
            <Globe className='h-4 w-4 text-gray-500' />
            <h4 className='text-sm font-medium text-gray-700'>Endpoint Configuration</h4>
          </div>
          <p className='mb-4 text-xs text-gray-500'>
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
            <p className='text-xs text-gray-500'>
              Enter the base domain for your endpoints without the protocol (https:// will be added
              automatically).
            </p>
          </div>
        </div>

        {/* Submit Button */}
        <div className='flex justify-end gap-3 border-t border-gray-200 pt-4'>
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
