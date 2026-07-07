import React from 'react';

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface DisplayNameFieldProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  isLoading: boolean;
}

export function DisplayNameField({ value, onChange, isLoading }: Readonly<DisplayNameFieldProps>) {
  return (
    <div className='space-y-2'>
      <Label htmlFor='full_name'>Full Name</Label>
      <Input
        id='full_name'
        value={value}
        onChange={onChange}
        placeholder='Your full name'
        disabled={isLoading}
      />
    </div>
  );
}
