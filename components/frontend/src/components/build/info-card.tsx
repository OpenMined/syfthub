import { memo } from 'react';

import Check from 'lucide-react/dist/esm/icons/check';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export interface InfoCardProps {
  title: string;
  items: string[];
}

// Memoized InfoCard component
export const InfoCard = memo(function InfoCard({ title, items }: Readonly<InfoCardProps>) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-sm font-medium'>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className='space-y-2'>
          {items.map((item, index) => (
            <li key={index} className='text-muted-foreground flex items-center gap-2 text-sm'>
              <Check className='h-4 w-4 text-green-500' />
              {item}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
});
