import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import Shield from 'lucide-react/dist/esm/icons/shield';
import Users from 'lucide-react/dist/esm/icons/users';
import Database from 'lucide-react/dist/esm/icons/database';
import TrendingUp from 'lucide-react/dist/esm/icons/trending-up';
import DollarSign from 'lucide-react/dist/esm/icons/dollar-sign';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Settings from 'lucide-react/dist/esm/icons/settings';
import UserPlus from 'lucide-react/dist/esm/icons/user-plus';
import Copy from 'lucide-react/dist/esm/icons/copy';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import ChevronRight from 'lucide-react/dist/esm/icons/chevron-right';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs } from '@/components/ui/tabs';
import { Modal } from '@/components/ui/modal';
import { Textarea } from '@/components/ui/textarea';
import { useAuth } from '@/context/auth-context';
import { getCollectiveBySlug, currentUserCollectives } from '@/lib/mock-data/collectives';
import { cn } from '@/lib/utils';

export default function CollectiveDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('overview');
  const [showJoinModal, setShowJoinModal] = useState(false);
  const [joinMessage, setJoinMessage] = useState('');

  if (!slug) {
    return <div>Invalid collective URL</div>;
  }

  const collective = getCollectiveBySlug(slug);

  if (!collective) {
    return (
      <div className="container mx-auto px-6 py-8 text-center">
        <h1 className="text-2xl font-bold mb-4">Collective Not Found</h1>
        <p className="text-muted-foreground mb-6">The collective you're looking for doesn't exist.</p>
        <Link to="/collectives">
          <Button>Browse Collectives</Button>
        </Link>
      </div>
    );
  }

  // Check if user is a member
  const userMembership = currentUserCollectives.find(c => c.collective.id === collective.id);
  const isAdmin = userMembership && (userMembership.role === 'admin' || userMembership.role === 'owner');

  const handleJoinRequest = () => {
    // Mock join request
    console.log('Join request submitted:', joinMessage);
    setShowJoinModal(false);
    setJoinMessage('');
    // In real implementation, this would send a request to the backend
  };

  const copyUnifiedEndpoint = () => {
    navigator.clipboard.writeText(`https://${collective.domain}/query`);
  };

  return (
    <div className="container mx-auto px-6 py-8 max-w-7xl">
      {/* Hero Section */}
      <div className="relative mb-8">
        {collective.bannerUrl && (
          <div className="h-48 rounded-lg overflow-hidden mb-6">
            <img
              src={collective.bannerUrl}
              alt=""
              className="w-full h-full object-cover"
            />
          </div>
        )}

        <div className="flex items-start justify-between">
          <div className="flex items-start gap-4">
            {collective.avatarUrl ? (
              <img
                src={collective.avatarUrl}
                alt={collective.name}
                className="w-20 h-20 rounded-lg"
              />
            ) : (
              <div className="w-20 h-20 rounded-lg bg-gradient-to-br from-primary/20 to-primary/10 flex items-center justify-center">
                <Users className="w-10 h-10 text-primary" />
              </div>
            )}

            <div>
              <h1 className="text-3xl font-bold flex items-center gap-2">
                {collective.name}
                {collective.isVerified && (
                  <Shield className="w-6 h-6 text-blue-500" aria-label="Verified" />
                )}
              </h1>
              <p className="text-muted-foreground mb-2">@{collective.slug}</p>
              <p className="text-muted-foreground max-w-3xl">{collective.description}</p>
              
              <div className="flex flex-wrap gap-2 mt-4">
                {collective.tags.map(tag => (
                  <Badge key={tag} variant="secondary">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
          </div>

          <div className="flex gap-2">
            {isAdmin && (
              <Link to={`/c/${collective.slug}/admin`}>
                <Button variant="outline">
                  <Settings className="w-4 h-4 mr-2" />
                  Manage
                </Button>
              </Link>
            )}
            {!userMembership && (
              <Button onClick={() => setShowJoinModal(true)}>
                <UserPlus className="w-4 h-4 mr-2" />
                {collective.membershipVisibility === 'open' ? 'Join' : 'Request to Join'}
              </Button>
            )}
            {userMembership && !isAdmin && (
              <Badge variant="default" className="py-2 px-4">
                <Users className="w-4 h-4 mr-2" />
                Member
              </Badge>
            )}
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        <Card className="p-4">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-muted-foreground" />
            <div>
              <p className="text-2xl font-bold">{collective.stats.memberCount}</p>
              <p className="text-xs text-muted-foreground">Members</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-muted-foreground" />
            <div>
              <p className="text-2xl font-bold">{collective.stats.endpointCount}</p>
              <p className="text-xs text-muted-foreground">Endpoints</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-muted-foreground" />
            <div>
              <p className="text-2xl font-bold">
                {collective.stats.monthlyQueries >= 1000000
                  ? `${(collective.stats.monthlyQueries / 1000000).toFixed(1)}M`
                  : collective.stats.monthlyQueries >= 1000
                  ? `${(collective.stats.monthlyQueries / 1000).toFixed(0)}K`
                  : collective.stats.monthlyQueries}
              </p>
              <p className="text-xs text-muted-foreground">Queries/mo</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-muted-foreground" />
            <div>
              <p className="text-2xl font-bold">
                {collective.stats.monthlyRevenue === 0
                  ? 'Free'
                  : collective.stats.monthlyRevenue >= 1000
                  ? `$${(collective.stats.monthlyRevenue / 1000).toFixed(0)}K`
                  : `$${collective.stats.monthlyRevenue}`}
              </p>
              <p className="text-xs text-muted-foreground">Revenue/mo</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-muted-foreground" />
            <div>
              <p className="text-2xl font-bold">{collective.stats.trustScore}%</p>
              <p className="text-xs text-muted-foreground">Trust Score</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Unified Endpoint Card */}
      {collective.capabilities.unifiedEndpoint && (
        <Card className="p-6 mb-8 bg-gradient-to-r from-primary/5 to-primary/10">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="font-semibold mb-2 flex items-center gap-2">
                <Globe className="w-5 h-5" />
                Unified Endpoint
              </h3>
              <p className="text-sm text-muted-foreground mb-3">
                Query all {collective.stats.endpointCount} endpoints through a single API
              </p>
              <div className="flex items-center gap-2">
                <code className="bg-background px-3 py-1 rounded text-sm">
                  https://{collective.domain}/query
                </code>
                <Button size="sm" variant="outline" onClick={copyUnifiedEndpoint}>
                  <Copy className="w-3 h-3" />
                </Button>
                <Button size="sm" variant="outline" asChild>
                  <a href={`https://${collective.domain}/docs`} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="w-3 h-3 mr-1" />
                    Docs
                  </a>
                </Button>
              </div>
            </div>
            <Badge variant="secondary">
              {collective.stats.endpointCount} APIs
            </Badge>
          </div>
        </Card>
      )}

      {/* Tabs Section */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="flex gap-4 border-b mb-6">
          {['overview', 'members', 'endpoints', 'pricing', 'policies'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "px-4 py-2 text-sm font-medium capitalize transition-colors",
                "border-b-2 -mb-[2px]",
                activeTab === tab
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="mt-6">
          {activeTab === 'overview' && (
            <div className="space-y-6">
              <Card className="p-6">
                <h3 className="font-semibold mb-4">Capabilities</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  {Object.entries(collective.capabilities).map(([key, enabled]) => (
                    <div key={key} className="flex items-center gap-2">
                      <div className={cn(
                        "w-2 h-2 rounded-full",
                        enabled ? "bg-green-500" : "bg-gray-300"
                      )} />
                      <span className="text-sm">
                        {key.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase())}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="p-6">
                <h3 className="font-semibold mb-4">Recent Activity</h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">New member joined</span>
                    <span>2 hours ago</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Endpoint added: Climate Sensor Network</span>
                    <span>5 hours ago</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Pricing tier updated</span>
                    <span>1 day ago</span>
                  </div>
                </div>
              </Card>
            </div>
          )}

          {activeTab === 'members' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {collective.members.map((member) => (
                <Card key={member.id} className="p-4">
                  <div className="flex items-center gap-3">
                    {member.avatarUrl ? (
                      <img
                        src={member.avatarUrl}
                        alt={member.displayName}
                        className="w-10 h-10 rounded-full"
                      />
                    ) : (
                      <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
                        <Users className="w-5 h-5 text-muted-foreground" />
                      </div>
                    )}
                    <div className="flex-1">
                      <p className="font-medium">{member.displayName}</p>
                      <p className="text-xs text-muted-foreground">@{member.username}</p>
                    </div>
                    <Badge variant={member.role === 'owner' ? 'default' : 'secondary'}>
                      {member.role}
                    </Badge>
                  </div>
                  <div className="mt-3 flex justify-between text-xs text-muted-foreground">
                    <span>{member.endpointCount} endpoints</span>
                    {member.contribution && (
                      <span>${(member.contribution / 1000).toFixed(1)}K contrib</span>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}

          {activeTab === 'endpoints' && (
            <div className="space-y-4">
              {collective.endpoints.map((endpoint) => (
                <Card key={endpoint.id} className="p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="font-medium flex items-center gap-2">
                        {endpoint.name}
                        {endpoint.usesCollectivePricing && (
                          <Badge variant="outline" className="text-xs">
                            Collective Pricing
                          </Badge>
                        )}
                      </h4>
                      <p className="text-sm text-muted-foreground mt-1">{endpoint.description}</p>
                      <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
                        <span>by @{endpoint.owner}</span>
                        <span>{(endpoint.queryCount / 1000).toFixed(0)}K queries</span>
                        <span>${endpoint.revenue} revenue</span>
                      </div>
                    </div>
                    <Badge variant="secondary">
                      {endpoint.type}
                    </Badge>
                  </div>
                </Card>
              ))}
            </div>
          )}

          {activeTab === 'pricing' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {collective.pricingTiers.map((tier) => (
                <Card 
                  key={tier.id} 
                  className={cn("p-6", tier.isDefault && "ring-2 ring-primary")}
                >
                  {tier.isDefault && (
                    <Badge className="mb-2">Most Popular</Badge>
                  )}
                  <h3 className="text-lg font-semibold mb-2">{tier.name}</h3>
                  <p className="text-sm text-muted-foreground mb-4">{tier.description}</p>
                  <div className="text-3xl font-bold mb-2">
                    {tier.price === 0 ? 'Free' : `$${tier.price}`}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {tier.unit.replace('-', ' ')}
                  </p>
                </Card>
              ))}
            </div>
          )}

          {activeTab === 'policies' && (
            <div className="space-y-4">
              {collective.policies.map((policy) => (
                <Card key={policy.id} className="p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="font-medium">{policy.name}</h4>
                      <p className="text-sm text-muted-foreground mt-1">{policy.description}</p>
                      <div className="flex items-center gap-2 mt-3">
                        <Badge variant="outline">{policy.type}</Badge>
                        <span className="text-xs text-muted-foreground">
                          Adopted by {policy.adoptionCount} members
                        </span>
                      </div>
                    </div>
                    <Button size="sm" variant="outline">
                      View Details
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </Tabs>

      {/* Join Request Modal */}
      <Modal
        isOpen={showJoinModal}
        onClose={() => setShowJoinModal(false)}
        title={`Request to Join ${collective.name}`}
      >
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Tell the collective administrators why you'd like to join and how you can contribute.
          </p>
          <Textarea
            placeholder="I would like to join because..."
            value={joinMessage}
            onChange={(e) => setJoinMessage(e.target.value)}
            rows={4}
          />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setShowJoinModal(false)}>
              Cancel
            </Button>
            <Button onClick={handleJoinRequest}>
              Send Request
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}