import type { Collective } from '@/lib/collectives-api';

import Users from 'lucide-react/dist/esm/icons/users';

interface CollectiveIconProps {
  collective: Pick<Collective, 'icon_url' | 'name'>;
  size?: 'md' | 'lg';
}

const SIZE = {
  md: { outer: 'h-10 w-10 shrink-0', inner: 'h-5 w-5' },
  lg: { outer: 'h-14 w-14 shrink-0', inner: 'h-7 w-7' }
} as const;

export function CollectiveIcon({ collective, size = 'md' }: Readonly<CollectiveIconProps>) {
  const { outer, inner } = SIZE[size];
  if (collective.icon_url) {
    return (
      <img
        src={collective.icon_url}
        alt={collective.name}
        className={`${outer} rounded-lg object-cover`}
      />
    );
  }
  return (
    <div
      className={`from-primary/20 to-primary/10 flex ${outer} items-center justify-center rounded-lg bg-gradient-to-br`}
    >
      <Users className={`text-primary ${inner}`} />
    </div>
  );
}
