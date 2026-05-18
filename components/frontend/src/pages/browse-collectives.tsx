import { useState } from 'react';
import { Link } from 'react-router-dom';
import Plus from 'lucide-react/dist/esm/icons/plus';
import Search from 'lucide-react/dist/esm/icons/search';
import Filter from 'lucide-react/dist/esm/icons/filter';
import Users from 'lucide-react/dist/esm/icons/users';
import Shield from 'lucide-react/dist/esm/icons/shield';

import { CollectiveCard } from '@/components/collectives/collective-card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { mockCollectives } from '@/lib/mock-data/collectives';

type FilterType = 'all' | 'legal-entity' | 'open' | 'request' | 'invite-only';
type SortType = 'relevance' | 'members' | 'newest';

export default function BrowseCollectivesPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<FilterType>('all');
  const [sortBy, setSortBy] = useState<SortType>('relevance');
  const [selectedTag, setSelectedTag] = useState<string>('');

  // Get unique tags from all collectives
  const allTags = Array.from(
    new Set(mockCollectives.flatMap(c => c.tags))
  ).slice(0, 8); // Limit to 8 most common tags

  // Filter and sort collectives
  let filteredCollectives = [...mockCollectives];

  // Apply search filter
  if (searchQuery) {
    const query = searchQuery.toLowerCase();
    filteredCollectives = filteredCollectives.filter(c =>
      c.name.toLowerCase().includes(query) ||
      c.description.toLowerCase().includes(query) ||
      c.tags.some(tag => tag.toLowerCase().includes(query))
    );
  }

  // Apply membership/legal entity filter
  if (filterType === 'legal-entity') {
    filteredCollectives = filteredCollectives.filter(c => c.hasLegalEntity);
  } else if (filterType !== 'all') {
    filteredCollectives = filteredCollectives.filter(c =>
      c.membershipVisibility === filterType
    );
  }

  // Apply tag filter
  if (selectedTag) {
    filteredCollectives = filteredCollectives.filter(c =>
      c.tags.includes(selectedTag)
    );
  }

  // Apply sorting
  filteredCollectives.sort((a, b) => {
    switch (sortBy) {
      case 'relevance':
        // Sort by legal entity status first, then member count
        if (a.hasLegalEntity !== b.hasLegalEntity) return a.hasLegalEntity ? -1 : 1;
        return b.stats.memberCount - a.stats.memberCount;
      case 'members':
        return b.stats.memberCount - a.stats.memberCount;
      case 'newest':
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      default:
        return 0;
    }
  });

  return (
    <div className="container mx-auto px-6 py-8 max-w-6xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-2">Browse Collectives</h1>
        <p className="text-muted-foreground">
          Find and join collectives that match your data and values
        </p>
      </div>

      {/* Search and Filters */}
      <div className="space-y-4 mb-8">
        {/* Search Bar */}
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search collectives..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
          <Link to="/collectives/create">
            <Button variant="outline">
              <Plus className="w-4 h-4 mr-2" />
              Create
            </Button>
          </Link>
        </div>

        {/* Filter Bar */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">Filter:</span>
          {(['all', 'legal-entity', 'open'] as FilterType[]).map(type => (
            <Button
              key={type}
              variant={filterType === type ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilterType(type)}
              className="h-8"
            >
              {type === 'legal-entity' && <Shield className="w-3 h-3 mr-1" />}
              {type === 'all' ? 'All' : type === 'legal-entity' ? 'Legal Entity' : 'Open to Join'}
            </Button>
          ))}
          
          <div className="ml-auto">
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortType)}
              className="h-8 px-3 text-sm border border-input bg-background rounded-md"
            >
              <option value="relevance">Most Relevant</option>
              <option value="members">Most Members</option>
              <option value="newest">Newest</option>
            </select>
          </div>
        </div>

        {/* Tag Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">Topics:</span>
          <Badge
            variant={!selectedTag ? 'default' : 'outline'}
            className="cursor-pointer text-xs"
            onClick={() => setSelectedTag('')}
          >
            All
          </Badge>
          {allTags.map(tag => (
            <Badge
              key={tag}
              variant={selectedTag === tag ? 'default' : 'outline'}
              className="cursor-pointer text-xs"
              onClick={() => setSelectedTag(tag === selectedTag ? '' : tag)}
            >
              {tag}
            </Badge>
          ))}
        </div>
      </div>

      {/* Results Count */}
      <div className="mb-4 text-sm text-muted-foreground">
        {filteredCollectives.length} collective{filteredCollectives.length !== 1 ? 's' : ''} found
      </div>

      {/* Collectives Grid */}
      {filteredCollectives.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredCollectives.map(collective => (
            <CollectiveCard key={collective.id} collective={collective} />
          ))}
        </div>
      ) : (
        <div className="text-center py-12">
          <Users className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground mb-4">No collectives found</p>
          {searchQuery || selectedTag || filterType !== 'all' ? (
            <Button 
              variant="outline"
              onClick={() => {
                setSearchQuery('');
                setSelectedTag('');
                setFilterType('all');
              }}
            >
              Clear Filters
            </Button>
          ) : (
            <Link to="/collectives/create">
              <Button>Create the First One</Button>
            </Link>
          )}
        </div>
      )}
    </div>
  );
}