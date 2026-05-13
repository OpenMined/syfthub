import { Link } from 'react-router-dom';
import Shield from 'lucide-react/dist/esm/icons/shield';
import Users from 'lucide-react/dist/esm/icons/users';
import Database from 'lucide-react/dist/esm/icons/database';
import TrendingUp from 'lucide-react/dist/esm/icons/trending-up';

import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import type { Collective } from '@/lib/mock-data/collectives';
import { cn } from '@/lib/utils';

interface CollectiveCardProps {
  collective: Collective;
}

export function CollectiveCard({ collective }: CollectiveCardProps) {
  const formatRevenue = (amount: number) => {
    if (amount === 0) return 'Free';
    if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
    if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
    return `$${amount}`;
  };

  const formatQueries = (count: number) => {
    if (count >= 1000000) return `${(count / 1000000).toFixed(1)}M`;
    if (count >= 1000) return `${(count / 1000).toFixed(0)}K`;
    return count.toString();
  };

  return (
    <Link to={`/c/${collective.slug}`}>
      <Card className="group relative overflow-hidden transition-all hover:shadow-lg hover:border-primary/50">
        {/* Banner Image */}
        {collective.bannerUrl && (
          <div className="h-24 overflow-hidden">
            <img
              src={collective.bannerUrl}
              alt=""
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            />
          </div>
        )}

        <div className="p-6">
          {/* Header */}
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              {collective.avatarUrl ? (
                <img
                  src={collective.avatarUrl}
                  alt={collective.name}
                  className="w-12 h-12 rounded-lg"
                />
              ) : (
                <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-primary/20 to-primary/10 flex items-center justify-center">
                  <Users className="w-6 h-6 text-primary" />
                </div>
              )}
              <div>
                <h3 className="font-semibold text-foreground flex items-center gap-2">
                  {collective.name}
                  {collective.isVerified && (
                    <Shield className="w-4 h-4 text-blue-500" aria-label="Verified" />
                  )}
                </h3>
                <p className="text-sm text-muted-foreground">@{collective.slug}</p>
              </div>
            </div>
          </div>

          {/* Description */}
          <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
            {collective.description}
          </p>

          {/* Stats Grid */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm">
                <span className="font-medium">{collective.stats.memberCount}</span>
                <span className="text-muted-foreground ml-1">members</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm">
                <span className="font-medium">{collective.stats.endpointCount}</span>
                <span className="text-muted-foreground ml-1">endpoints</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm">
                <span className="font-medium">{formatQueries(collective.stats.monthlyQueries)}</span>
                <span className="text-muted-foreground ml-1">queries/mo</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm">
                <span className="font-medium">{formatRevenue(collective.stats.monthlyRevenue)}</span>
                <span className="text-muted-foreground ml-1">/month</span>
              </span>
            </div>
          </div>

          {/* Tags */}
          <div className="flex flex-wrap gap-1.5">
            {collective.tags.slice(0, 3).map(tag => (
              <Badge key={tag} variant="secondary" className="text-xs">
                {tag}
              </Badge>
            ))}
            {collective.tags.length > 3 && (
              <Badge variant="secondary" className="text-xs">
                +{collective.tags.length - 3}
              </Badge>
            )}
          </div>

          {/* Membership Type Badge */}
          <div className="absolute top-4 right-4">
            <Badge
              variant="outline"
              className={cn(
                "text-xs",
                collective.membershipVisibility === 'open' && "border-green-500 text-green-600",
                collective.membershipVisibility === 'request' && "border-yellow-500 text-yellow-600",
                collective.membershipVisibility === 'invite-only' && "border-purple-500 text-purple-600"
              )}
            >
              {collective.membershipVisibility === 'open' && 'Open'}
              {collective.membershipVisibility === 'request' && 'Request'}
              {collective.membershipVisibility === 'invite-only' && 'Invite Only'}
            </Badge>
          </div>
        </div>
      </Card>
    </Link>
  );
}