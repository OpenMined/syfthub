import { Link } from 'react-router-dom';
import Shield from 'lucide-react/dist/esm/icons/shield';
import Users from 'lucide-react/dist/esm/icons/users';
import Database from 'lucide-react/dist/esm/icons/database';
import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';

import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import type { Collective } from '@/lib/mock-data/collectives';
import { cn } from '@/lib/utils';

interface CollectiveCardProps {
  collective: Collective;
}

export function CollectiveCard({ collective }: CollectiveCardProps) {
  return (
    <Link to={`/c/${collective.slug}`}>
      <Card className="group relative overflow-hidden transition-all hover:shadow-lg hover:border-primary/50 p-5">
        {/* Header with Avatar and Name */}
        <div className="flex items-start gap-3 mb-3">
          {collective.avatarUrl ? (
            <img
              src={collective.avatarUrl}
              alt={collective.name}
              className="w-10 h-10 rounded-lg shrink-0"
            />
          ) : (
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary/20 to-primary/10 flex items-center justify-center shrink-0">
              <Users className="w-5 h-5 text-primary" />
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-foreground truncate">
                {collective.name}
              </h3>
              {collective.verified && (
                <CheckCircle className="w-4 h-4 text-green-500 shrink-0" aria-label="Verified" />
              )}
            </div>
            <p className="text-sm text-muted-foreground">@{collective.slug}</p>
          </div>
        </div>

        {/* Description */}
        <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
          {collective.description}
        </p>

        {/* Simple Stats */}
        <div className="flex items-center gap-4 text-sm text-muted-foreground mb-3">
          <div className="flex items-center gap-1">
            <Users className="w-3.5 h-3.5" />
            <span>{collective.stats.memberCount}</span>
          </div>
          <div className="flex items-center gap-1">
            <Database className="w-3.5 h-3.5" />
            <span>{collective.stats.endpointCount}</span>
          </div>
          {collective.hasLegalEntity && (
            <div className="flex items-center gap-1">
              <Shield className="w-3.5 h-3.5 text-blue-500" />
              <span className="text-xs">Legal Entity</span>
            </div>
          )}
        </div>

        {/* Tags */}
        <div className="flex flex-wrap gap-1.5">
          {collective.tags.slice(0, 3).map(tag => (
            <Badge key={tag} variant="secondary" className="text-xs">
              {tag}
            </Badge>
          ))}
          <Badge 
            variant="outline" 
            className={cn(
              "text-xs ml-auto",
              collective.membershipVisibility === 'open' && "text-green-600",
              collective.membershipVisibility === 'request' && "text-yellow-600",
              collective.membershipVisibility === 'invite-only' && "text-purple-600"
            )}
          >
            {collective.membershipVisibility === 'open' && 'Open'}
            {collective.membershipVisibility === 'request' && 'Request'}
            {collective.membershipVisibility === 'invite-only' && 'Invite'}
          </Badge>
        </div>
      </Card>
    </Link>
  );
}