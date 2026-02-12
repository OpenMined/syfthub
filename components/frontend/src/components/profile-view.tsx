import { useEffect, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Calendar from 'lucide-react/dist/esm/icons/calendar';
import Check from 'lucide-react/dist/esm/icons/check';
import Edit3 from 'lucide-react/dist/esm/icons/edit-3';
import Key from 'lucide-react/dist/esm/icons/key';
import Lock from 'lucide-react/dist/esm/icons/lock';
import Mail from 'lucide-react/dist/esm/icons/mail';
import Save from 'lucide-react/dist/esm/icons/save';
import Shield from 'lucide-react/dist/esm/icons/shield';
import UserIcon from 'lucide-react/dist/esm/icons/user';
import X from 'lucide-react/dist/esm/icons/x';

import { useAuth } from '@/context/auth-context';
import { changePasswordAPI, updateUserProfileAPI } from '@/lib/sdk-client';

import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';

// Helper functions moved outside component for consistent-function-scoping
function formatDate(dateString: string) {
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
}

function getRoleBadgeColor(role: string) {
  switch (role) {
    case 'admin': {
      return 'bg-red-100 text-red-800 border-red-200';
    }
    case 'user': {
      return 'bg-blue-100 text-blue-800 border-blue-200';
    }
    case 'guest': {
      return 'bg-muted text-muted-foreground border-border';
    }
    default: {
      return 'bg-muted text-muted-foreground border-border';
    }
  }
}

interface ProfileEditData {
  full_name: string;
  email: string;
}

interface PasswordChangeData {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export function ProfileView() {
  const { user, updateUser } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Profile edit form state
  const [editData, setEditData] = useState<ProfileEditData>({
    full_name: user?.full_name ?? '',
    email: user?.email ?? ''
  });

  // Sync edit data when user context changes (e.g., after successful update)
  useEffect(() => {
    if (user) {
      setEditData({
        full_name: user.full_name || '',
        email: user.email || ''
      });
    }
  }, [user]);

  // Password change form state
  const [passwordData, setPasswordData] = useState<PasswordChangeData>({
    current_password: '',
    new_password: '',
    confirm_password: ''
  });

  if (!user) {
    return (
      <div className='flex min-h-screen items-center justify-center'>
        <div className='text-center'>
          <AlertCircle className='mx-auto mb-4 h-12 w-12 text-red-500' />
          <h2 className='text-foreground mb-2 text-xl font-semibold'>Access Denied</h2>
          <p className='text-muted-foreground'>You need to be logged in to view your profile.</p>
        </div>
      </div>
    );
  }

  const handleProfileSave = async () => {
    try {
      setIsLoading(true);
      setError(null);
      setSuccess(null);

      // Update profile and get the updated user directly from the response
      const updatedUser = await updateUserProfileAPI({
        full_name: editData.full_name,
        email: editData.email
      });

      // Update auth context directly with the response data
      updateUser(updatedUser);

      setSuccess('Profile updated successfully!');
      setIsEditing(false);

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

  const handlePasswordChange = async () => {
    try {
      setError(null);
      setSuccess(null);

      if (passwordData.new_password !== passwordData.confirm_password) {
        setError('New passwords do not match');
        return;
      }

      if (passwordData.new_password.length < 8) {
        setError('Password must be at least 8 characters long');
        return;
      }

      setIsLoading(true);

      await changePasswordAPI({
        current_password: passwordData.current_password,
        new_password: passwordData.new_password
      });

      setSuccess('Password changed successfully!');
      setIsChangingPassword(false);
      setPasswordData({
        current_password: '',
        new_password: '',
        confirm_password: ''
      });

      // Clear success message after 3 seconds
      setTimeout(() => {
        setSuccess(null);
      }, 3000);
    } catch (error_) {
      setError(error_ instanceof Error ? error_.message : 'Failed to change password');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className='bg-muted min-h-screen py-8'>
      <div className='mx-auto max-w-4xl px-6'>
        {/* Header */}
        <div className='mb-8'>
          <h1 className='text-foreground text-3xl font-bold'>Profile Settings</h1>
          <p className='text-muted-foreground mt-2'>
            Manage your account information and security settings.
          </p>
        </div>

        {/* Success/Error Messages */}
        <AnimatePresence>
          {success ? (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className='mb-6 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-4'
            >
              <Check className='h-5 w-5 text-green-600' />
              <span className='text-green-800'>{success}</span>
            </motion.div>
          ) : null}

          {error ? (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className='mb-6 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-4'
            >
              <AlertCircle className='h-5 w-5 text-red-600' />
              <span className='text-red-800'>{error}</span>
            </motion.div>
          ) : null}
        </AnimatePresence>

        <div className='grid gap-8 lg:grid-cols-2'>
          {/* Profile Information */}
          <div className='border-border bg-card rounded-lg border shadow-sm'>
            <div className='border-border border-b px-6 py-4'>
              <div className='flex items-center justify-between'>
                <h2 className='text-foreground text-lg font-semibold'>Profile Information</h2>
                {isEditing ? null : (
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => {
                      setIsEditing(true);
                    }}
                    className='flex items-center gap-2'
                  >
                    <Edit3 className='h-4 w-4' />
                    Edit
                  </Button>
                )}
              </div>
            </div>

            <div className='space-y-6 p-6'>
              {/* Avatar */}
              <div className='flex items-center gap-4'>
                <div className='flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-purple-600'>
                  {user.avatar_url ? (
                    <img
                      src={user.avatar_url}
                      alt={user.name}
                      width={64}
                      height={64}
                      loading='lazy'
                      className='h-16 w-16 rounded-full object-cover'
                    />
                  ) : (
                    <UserIcon className='h-8 w-8 text-white' aria-hidden='true' />
                  )}
                </div>
                <div>
                  <h3 className='text-foreground text-lg font-medium'>{user.name}</h3>
                  <p className='text-muted-foreground text-sm'>@{user.username}</p>
                </div>
              </div>

              {isEditing ? (
                /* Edit Form */
                <div className='space-y-4'>
                  <div>
                    <Label htmlFor='full_name'>Full Name</Label>
                    <Input
                      id='full_name'
                      value={editData.full_name}
                      onChange={(e) => {
                        setEditData((previous) => ({ ...previous, full_name: e.target.value }));
                      }}
                      placeholder='Enter your full name'
                    />
                  </div>

                  <div>
                    <Label htmlFor='email'>Email</Label>
                    <Input
                      id='email'
                      type='email'
                      value={editData.email}
                      onChange={(e) => {
                        setEditData((previous) => ({ ...previous, email: e.target.value }));
                      }}
                      placeholder='Enter your email'
                    />
                  </div>

                  <div className='flex gap-2'>
                    <Button
                      onClick={handleProfileSave}
                      disabled={isLoading}
                      className='flex items-center gap-2'
                    >
                      <Save className='h-4 w-4' aria-hidden='true' />
                      {isLoading ? 'Saving…' : 'Save Changes'}
                    </Button>
                    <Button
                      variant='outline'
                      onClick={() => {
                        setIsEditing(false);
                        setEditData({
                          full_name: user.full_name,
                          email: user.email
                        });
                      }}
                    >
                      <X className='mr-2 h-4 w-4' />
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                /* View Mode */
                <div className='space-y-4'>
                  <div className='flex items-center gap-3'>
                    <Mail className='text-muted-foreground h-5 w-5' />
                    <div>
                      <p className='text-foreground text-sm font-medium'>{user.email}</p>
                      <p className='text-muted-foreground text-xs'>Email address</p>
                    </div>
                  </div>

                  <div className='flex items-center gap-3'>
                    <Shield className='text-muted-foreground h-5 w-5' />
                    <div>
                      <Badge className={getRoleBadgeColor(user.role)}>
                        {user.role.charAt(0).toUpperCase() + user.role.slice(1)}
                      </Badge>
                      <p className='text-muted-foreground mt-1 text-xs'>Account role</p>
                    </div>
                  </div>

                  <div className='flex items-center gap-3'>
                    <Calendar className='text-muted-foreground h-5 w-5' />
                    <div>
                      <p className='text-foreground text-sm font-medium'>
                        {formatDate(user.created_at)}
                      </p>
                      <p className='text-muted-foreground text-xs'>Member since</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Security Settings */}
          <div className='border-border bg-card rounded-lg border shadow-sm'>
            <div className='border-border border-b px-6 py-4'>
              <div className='flex items-center justify-between'>
                <h2 className='text-foreground text-lg font-semibold'>Security Settings</h2>
                {isChangingPassword ? null : (
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => {
                      setIsChangingPassword(true);
                    }}
                    className='flex items-center gap-2'
                  >
                    <Lock className='h-4 w-4' aria-hidden='true' />
                    Change Password
                  </Button>
                )}
              </div>
            </div>

            <div className='space-y-6 p-6'>
              {isChangingPassword ? (
                /* Password Change Form */
                <div className='space-y-4'>
                  <div>
                    <Label htmlFor='current_password'>Current Password</Label>
                    <Input
                      id='current_password'
                      type='password'
                      value={passwordData.current_password}
                      onChange={(e) => {
                        setPasswordData((previous) => ({
                          ...previous,
                          current_password: e.target.value
                        }));
                      }}
                      placeholder='Enter your current password'
                    />
                  </div>

                  <div>
                    <Label htmlFor='new_password'>New Password</Label>
                    <Input
                      id='new_password'
                      type='password'
                      value={passwordData.new_password}
                      onChange={(e) => {
                        setPasswordData((previous) => ({
                          ...previous,
                          new_password: e.target.value
                        }));
                      }}
                      placeholder='Enter your new password'
                    />
                  </div>

                  <div>
                    <Label htmlFor='confirm_password'>Confirm New Password</Label>
                    <Input
                      id='confirm_password'
                      type='password'
                      value={passwordData.confirm_password}
                      onChange={(e) => {
                        setPasswordData((previous) => ({
                          ...previous,
                          confirm_password: e.target.value
                        }));
                      }}
                      placeholder='Confirm your new password'
                    />
                  </div>

                  <div className='flex gap-2'>
                    <Button
                      onClick={handlePasswordChange}
                      disabled={isLoading}
                      className='flex items-center gap-2'
                    >
                      <Save className='h-4 w-4' aria-hidden='true' />
                      {isLoading ? 'Changing…' : 'Change Password'}
                    </Button>
                    <Button
                      variant='outline'
                      onClick={() => {
                        setIsChangingPassword(false);
                        setPasswordData({
                          current_password: '',
                          new_password: '',
                          confirm_password: ''
                        });
                      }}
                    >
                      <X className='mr-2 h-4 w-4' />
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                /* Security Info */
                <div className='space-y-4'>
                  <div className='flex items-center gap-3'>
                    <Key className='text-muted-foreground h-5 w-5' />
                    <div>
                      <p className='text-foreground text-sm font-medium'>Password</p>
                      <p className='text-muted-foreground text-xs'>
                        Last updated: {formatDate(user.updated_at)}
                      </p>
                    </div>
                  </div>

                  <div className='rounded-lg border border-blue-200 bg-blue-50 p-4'>
                    <div className='flex items-start gap-3'>
                      <Shield className='mt-0.5 h-5 w-5 text-blue-600' />
                      <div>
                        <h3 className='text-sm font-medium text-blue-900'>Account Security</h3>
                        <p className='mt-1 text-xs text-blue-700'>
                          Your account is secured with industry-standard encryption and JWT tokens.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
