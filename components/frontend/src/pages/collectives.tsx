import { useState } from 'react';
import { Link } from 'react-router-dom';
import Plus from 'lucide-react/dist/esm/icons/plus';
import Search from 'lucide-react/dist/esm/icons/search';
import Filter from 'lucide-react/dist/esm/icons/filter';
import Users from 'lucide-react/dist/esm/icons/users';
import TrendingUp from 'lucide-react/dist/esm/icons/trending-up';

import { CollectiveCard } from '@/components/collectives/collective-card';
import { CollectiveStats } from '@/components/collectives/collective-stats';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select } from '@/components/ui/select';
import { PageHeader } from '@/components/ui/page-header';
import { mockCollectives, getCollectiveStats } from '@/lib/mock-data/collectives';
import { cn } from '@/lib/utils';

type FilterType = 'all' | 'open' | 'request' | 'invite-only';
type SortType = 'members' | 'endpoints' | 'queries' | 'revenue' | 'newest';

export default function CollectivesPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<FilterType>('all');
  const [sortBy, setSortBy] = useState<SortType>('members');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  // Get unique tags from all collectives
  const allTags = Array.from(
    new Set(mockCollectives.flatMap(c => c.tags))
  );

  // Filter and sort collectives
  let filteredCollectives = [...mockCollectives];

  // Apply search filter
  if (searchQuery) {
    const query = searchQuery.toLowerCase();
    filteredCollectives = filteredCollectives.filter(c =>
      c.name.toLowerCase().includes(query) ||
      c.description.toLowerCase().includes(query) ||
      c.slug.toLowerCase().includes(query)
    );
  }

  // Apply membership filter
  if (filterType !== 'all') {
    filteredCollectives = filteredCollectives.filter(c =>
      c.membershipVisibility === filterType
    );
  }

  // Apply tag filter
  if (selectedTags.length > 0) {
    filteredCollectives = filteredCollectives.filter(c =>
      selectedTags.some(tag => c.tags.includes(tag))
    );
  }

  // Apply sorting
  filteredCollectives.sort((a, b) => {
    switch (sortBy) {
      case 'members':
        return b.stats.memberCount - a.stats.memberCount;
      case 'endpoints':
        return b.stats.endpointCount - a.stats.endpointCount;
      case 'queries':
        return b.stats.monthlyQueries - a.stats.monthlyQueries;
      case 'revenue':
        return b.stats.monthlyRevenue - a.stats.monthlyRevenue;
      case 'newest':
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      default:
        return 0;
    }
  });

  const stats = getCollectiveStats();

  const toggleTag = (tag: string) => {
    setSelectedTags(prev =>
      prev.includes(tag)
        ? prev.filter(t => t !== tag)
        : [...prev, tag]
    );
  };

  return (
    <div className="container mx-auto px-6 py-8 max-w-7xl">
      <PageHeader title="Data Collectives" />
      <p className="text-muted-foreground text-center mb-8 max-w-3xl mx-auto">
        Join forces with organizations to share data, infrastructure, and bargaining power in the AI economy
      </p>

      {/* Stats Overview */}
      <div className="mb-8">
        <CollectiveStats stats={stats} />
      </div>

      {/* Hero Section */}
      <div className="bg-gradient-to-r from-primary/10 to-primary/5 rounded-lg p-8 mb-8">
        <div className="max-w-3xl">
          <h2 className="text-2xl font-bold mb-3">Transform Your Data into Collective Power</h2>
          <p className="text-muted-foreground mb-6">
            Data collectives enable small data owners to compete with Big Tech by pooling resources, 
            sharing infrastructure, and negotiating better terms together. Join a collective or create 
            your own to unlock the true value of your data.
          </p>
          <div className="flex gap-3">
            <Link to="/collectives/create">
              <Button size="lg">
                <Plus className="w-4 h-4 mr-2" />
                Create Collective
              </Button>
            </Link>
            <Button size="lg" variant="outline">
              Learn More
            </Button>
          </div>
        </div>
      </div>

      {/* Filters and Search */}
      <div className="mb-6 space-y-4">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search collectives..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>

          {/* Membership Filter */}
          <div className="flex gap-2">
            {(['all', 'open', 'request', 'invite-only'] as FilterType[]).map(type => (
              <Button
                key={type}
                variant={filterType === type ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFilterType(type)}
              >
                {type === 'all' ? 'All' : type.replace('-', ' ')}
              </Button>
            ))}
          </div>

          {/* Sort Dropdown */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortType)}
            className="px-3 py-2 border border-input bg-background rounded-md text-sm"
          >
            <option value="members">Most Members</option>
            <option value="endpoints">Most Endpoints</option>
            <option value="queries">Most Active</option>
            <option value="revenue">Highest Revenue</option>
            <option value="newest">Newest First</option>
          </select>
        </div>

        {/* Tag Filter */}
        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Tags:</span>
          {allTags.map(tag => (
            <Badge
              key={tag}
              variant={selectedTags.includes(tag) ? 'default' : 'outline'}
              className="cursor-pointer"
              onClick={() => toggleTag(tag)}
            >
              {tag}
            </Badge>
          ))}
        </div>
      </div>

      {/* Results Count */}
      <div className="mb-4 text-sm text-muted-foreground">
        Showing {filteredCollectives.length} of {mockCollectives.length} collectives
      </div>

      {/* Collectives Grid */}
      {filteredCollectives.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {filteredCollectives.map(collective => (
            <CollectiveCard key={collective.id} collective={collective} />
          ))}
        </div>
      ) : (
        <div className="text-center py-12">
          <Users className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">No collectives found matching your criteria</p>
        </div>
      )}

      {/* Featured Collectives Section */}
      <div className="mt-12 border-t pt-12">
        <h2 className="text-xl font-semibold mb-6">Why Join a Collective?</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="text-center">
            <div className="w-12 h-12 rounded-full bg-blue-500/10 flex items-center justify-center mx-auto mb-3">
              <Users className="w-6 h-6 text-blue-500" />
            </div>
            <h3 className="font-medium mb-2">Shared Infrastructure</h3>
            <p className="text-sm text-muted-foreground">
              Enterprise-grade hosting and APIs at 1/100th the cost
            </p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 rounded-full bg-green-500/10 flex items-center justify-center mx-auto mb-3">
              <Search className="w-6 h-6 text-green-500" />
            </div>
            <h3 className="font-medium mb-2">Better Discovery</h3>
            <p className="text-sm text-muted-foreground">
              Get found through collective's unified endpoint and reputation
            </p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 rounded-full bg-purple-500/10 flex items-center justify-center mx-auto mb-3">
              <TrendingUp className="w-6 h-6 text-purple-500" />
            </div>
            <h3 className="font-medium mb-2">Collective Bargaining</h3>
            <p className="text-sm text-muted-foreground">
              Negotiate better prices and terms as a group
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}