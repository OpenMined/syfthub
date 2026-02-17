import React, { memo } from 'react';

export interface SectionProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}

// Memoized Section component to prevent unnecessary re-renders
export const Section = memo(function Section({
  title,
  description,
  icon,
  children
}: Readonly<SectionProps>) {
  return (
    <div className='space-y-4'>
      <div className='flex items-start gap-3'>
        <div className='border-border text-foreground bg-card rounded-lg border p-2'>{icon}</div>
        <div>
          <h3 className='text-foreground text-lg font-medium'>{title}</h3>
          <p className='text-muted-foreground text-sm'>{description}</p>
        </div>
      </div>
      {children}
    </div>
  );
});
