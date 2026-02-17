import React from 'react';

import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import Check from 'lucide-react/dist/esm/icons/check';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface AvailabilityState {
  checking: boolean;
  available: boolean | null;
  message: string | null;
}

export interface UsernameFieldProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  isLoading: boolean;
  availability: AvailabilityState;
}

export function UsernameField({
  value,
  onChange,
  isLoading,
  availability
}: Readonly<UsernameFieldProps>) {
  return (
    <div className='space-y-2'>
      <Label htmlFor='username'>Username</Label>
      <div className='relative'>
        <Input
          id='username'
          value={value}
          onChange={onChange}
          placeholder='your-username'
          disabled={isLoading}
          className={(() => {
            if (availability.available === false) {
              return 'border-red-300 focus:border-red-500 focus:ring-red-500';
            }
            if (availability.available === true) {
              return 'border-green-300 focus:border-green-500 focus:ring-green-500';
            }
            return '';
          })()}
        />
        {availability.checking ? (
          <div className='absolute top-1/2 right-3 -translate-y-1/2'>
            <Loader2 className='text-muted-foreground h-4 w-4 animate-spin' />
          </div>
        ) : null}
        {!availability.checking && availability.available === true ? (
          <div className='absolute top-1/2 right-3 -translate-y-1/2'>
            <Check className='h-4 w-4 text-green-500' />
          </div>
        ) : null}
        {!availability.checking && availability.available === false ? (
          <div className='absolute top-1/2 right-3 -translate-y-1/2'>
            <AlertCircle className='h-4 w-4 text-red-500' />
          </div>
        ) : null}
      </div>
      {availability.message ? (
        <p
          className={`text-xs ${
            availability.available === false ? 'text-red-600' : 'text-green-600'
          }`}
        >
          {availability.message}
        </p>
      ) : null}
    </div>
  );
}
