import { Link } from 'react-router-dom';
import Shield from 'lucide-react/dist/esm/icons/shield';
import Users from 'lucide-react/dist/esm/icons/users';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface CollectiveBadgeProps {
  name: string;
  slug: string;
  isVerified?: boolean;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
  className?: string;
}

export function CollectiveBadge({ 
  name, 
  slug, 
  isVerified = false,
  size = 'md',
  showIcon = true,
  className 
}: CollectiveBadgeProps) {
  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-0.5',
    lg: 'text-base px-3 py-1'
  };

  const iconSize = {
    sm: 'w-3 h-3',
    md: 'w-3.5 h-3.5',
    lg: 'w-4 h-4'
  };

  return (
    <Link to={`/c/${slug}`} className="inline-flex">
      <Badge 
        variant="secondary" 
        className={cn(
          "hover:bg-secondary/80 transition-colors flex items-center gap-1.5",
          sizeClasses[size],
          className
        )}
      >
        {showIcon && <Users className={iconSize[size]} />}
        <span>{name}</span>
        {isVerified && (
          <Shield className={cn(iconSize[size], "text-blue-500 ml-0.5")} aria-label="Verified" />
        )}
      </Badge>
    </Link>
  );
}