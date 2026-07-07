import React from 'react';

import User from 'lucide-react/dist/esm/icons/user';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface AvatarSectionProps {
  avatarUrl: string;
  fullName: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  isLoading: boolean;
}

export function AvatarSection({
  avatarUrl,
  fullName,
  onChange,
  isLoading
}: Readonly<AvatarSectionProps>) {
  const avatarPreviewUrl =
    avatarUrl ||
    `https://ui-avatars.com/api/?name=${encodeURIComponent(fullName || 'User')}&background=272532&color=fff`;

  return (
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
                  `https://ui-avatars.com/api/?name=${encodeURIComponent(fullName || 'User')}&background=272532&color=fff`;
              }}
            />
          ) : (
            <User className='h-8 w-8 text-white' aria-hidden='true' />
          )}
        </div>
        <div className='flex-1'>
          <Input
            type='url'
            value={avatarUrl}
            onChange={onChange}
            placeholder='https://example.com/your-avatar.png'
            disabled={isLoading}
          />
          <p className='text-muted-foreground mt-1 text-xs'>
            Enter a URL to your profile picture. Leave blank to use an auto-generated avatar.
          </p>
        </div>
      </div>
    </div>
  );
}
