import React, { useEffect, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  Calendar,
  Check,
  Edit3,
  Key,
  Lock,
  Mail,
  Save,
  Shield,
  User as UserIcon,
  X
} from 'lucide-react';

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
      return 'bg-gray-100 text-gray-800 border-gray-200';
    }
    default: {
      return 'bg-gray-100 text-gray-800 border-gray-200';
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
          <h2 className='mb-2 text-xl font-semibold text-gray-900'>Access Denied</h2>
          <p className='text-gray-600'>You need to be logged in to view your profile.</p>
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
    <div className='min-h-screen bg-gray-50 py-8'>
      <div className='mx-auto max-w-4xl px-6'>
        {/* Header */}
        <div className='mb-8'>
          <h1 className='text-3xl font-bold text-gray-900'>Profile Settings</h1>
          <p className='mt-2 text-gray-600'>
            Manage your account information and security settings.
          </p>
        </div>

        {/* Success/Error Messages */}
        <AnimatePresence>
          {success && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className='mb-6 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-4'
            >
              <Check className='h-5 w-5 text-green-600' />
              <span className='text-green-800'>{success}</span>
            </motion.div>
          )}

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className='mb-6 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-4'
            >
              <AlertCircle className='h-5 w-5 text-red-600' />
              <span className='text-red-800'>{error}</span>
            </motion.div>
          )}
        </AnimatePresence>

        <div className='grid gap-8 lg:grid-cols-2'>
          {/* Profile Information */}
          <div className='rounded-lg border border-gray-200 bg-white shadow-sm'>
            <div className='border-b border-gray-200 px-6 py-4'>
              <div className='flex items-center justify-between'>
                <h2 className='text-lg font-semibold text-gray-900'>Profile Information</h2>
                {!isEditing && (
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
                      className='h-16 w-16 rounded-full object-cover'
                    />
                  ) : (
                    <UserIcon className='h-8 w-8 text-white' />
                  )}
                </div>
                <div>
                  <h3 className='text-lg font-medium text-gray-900'>{user.name}</h3>
                  <p className='text-sm text-gray-500'>@{user.username}</p>
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
                        setEditData({ ...editData, full_name: e.target.value });
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
                        setEditData({ ...editData, email: e.target.value });
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
                      <Save className='h-4 w-4' />
                      {isLoading ? 'Saving...' : 'Save Changes'}
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
                    <Mail className='h-5 w-5 text-gray-400' />
                    <div>
                      <p className='text-sm font-medium text-gray-900'>{user.email}</p>
                      <p className='text-xs text-gray-500'>Email address</p>
                    </div>
                  </div>

                  <div className='flex items-center gap-3'>
                    <Shield className='h-5 w-5 text-gray-400' />
                    <div>
                      <Badge className={getRoleBadgeColor(user.role)}>
                        {user.role.charAt(0).toUpperCase() + user.role.slice(1)}
                      </Badge>
                      <p className='mt-1 text-xs text-gray-500'>Account role</p>
                    </div>
                  </div>

                  <div className='flex items-center gap-3'>
                    <Calendar className='h-5 w-5 text-gray-400' />
                    <div>
                      <p className='text-sm font-medium text-gray-900'>
                        {formatDate(user.created_at)}
                      </p>
                      <p className='text-xs text-gray-500'>Member since</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Security Settings */}
          <div className='rounded-lg border border-gray-200 bg-white shadow-sm'>
            <div className='border-b border-gray-200 px-6 py-4'>
              <div className='flex items-center justify-between'>
                <h2 className='text-lg font-semibold text-gray-900'>Security Settings</h2>
                {!isChangingPassword && (
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => {
                      setIsChangingPassword(true);
                    }}
                    className='flex items-center gap-2'
                  >
                    <Lock className='h-4 w-4' />
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
                        setPasswordData({ ...passwordData, current_password: e.target.value });
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
                        setPasswordData({ ...passwordData, new_password: e.target.value });
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
                        setPasswordData({ ...passwordData, confirm_password: e.target.value });
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
                      <Save className='h-4 w-4' />
                      {isLoading ? 'Changing...' : 'Change Password'}
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
                    <Key className='h-5 w-5 text-gray-400' />
                    <div>
                      <p className='text-sm font-medium text-gray-900'>Password</p>
                      <p className='text-xs text-gray-500'>
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
