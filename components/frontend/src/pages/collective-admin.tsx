import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import Users from 'lucide-react/dist/esm/icons/users';
import UserCheck from 'lucide-react/dist/esm/icons/user-check';
import UserX from 'lucide-react/dist/esm/icons/user-x';
import Settings from 'lucide-react/dist/esm/icons/settings';
import Database from 'lucide-react/dist/esm/icons/database';
import DollarSign from 'lucide-react/dist/esm/icons/dollar-sign';
import TrendingUp from 'lucide-react/dist/esm/icons/trending-up';
import Shield from 'lucide-react/dist/esm/icons/shield';
import Mail from 'lucide-react/dist/esm/icons/mail';
import Calendar from 'lucide-react/dist/esm/icons/calendar';
import MoreVertical from 'lucide-react/dist/esm/icons/more-vertical';
import Plus from 'lucide-react/dist/esm/icons/plus';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/context/auth-context';
import { getCollectiveBySlug, currentUserCollectives } from '@/lib/mock-data/collectives';
import { cn } from '@/lib/utils';

export default function CollectiveAdminPage() {
  const { slug } = useParams<{ slug: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('members');

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

  // Check if user is admin
  const userMembership = currentUserCollectives.find(c => c.collective.id === collective.id);
  const isAdmin = userMembership && (userMembership.role === 'admin' || userMembership.role === 'owner');

  if (!isAdmin) {
    return (
      <div className="container mx-auto px-6 py-8 text-center">
        <h1 className="text-2xl font-bold mb-4">Access Denied</h1>
        <p className="text-muted-foreground mb-6">You don't have permission to manage this collective.</p>
        <Link to={`/c/${collective.slug}`}>
          <Button>Go to Collective Page</Button>
        </Link>
      </div>
    );
  }

  const handleApproveRequest = (requestId: string) => {
    console.log('Approving request:', requestId);
    // In real implementation, this would update the backend
  };

  const handleRejectRequest = (requestId: string) => {
    console.log('Rejecting request:', requestId);
    // In real implementation, this would update the backend
  };

  const handleRemoveMember = (memberId: string) => {
    console.log('Removing member:', memberId);
    // In real implementation, this would update the backend
  };

  return (
    <div className="container mx-auto px-6 py-8 max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <Link to={`/c/${collective.slug}`} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4">
          <ArrowLeft className="w-4 h-4" />
          Back to {collective.name}
        </Link>
        
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              Manage {collective.name}
              {collective.isVerified && (
                <Shield className="w-6 h-6 text-blue-500" aria-label="Verified" />
              )}
            </h1>
            <p className="text-muted-foreground mt-1">Administer collective settings, members, and policies</p>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Users className="w-8 h-8 text-blue-500" />
            <div>
              <p className="text-2xl font-bold">{collective.stats.memberCount}</p>
              <p className="text-xs text-muted-foreground">Total Members</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <UserCheck className="w-8 h-8 text-yellow-500" />
            <div>
              <p className="text-2xl font-bold">{collective.pendingRequests.length}</p>
              <p className="text-xs text-muted-foreground">Pending Requests</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <Database className="w-8 h-8 text-purple-500" />
            <div>
              <p className="text-2xl font-bold">{collective.stats.endpointCount}</p>
              <p className="text-xs text-muted-foreground">Active Endpoints</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <DollarSign className="w-8 h-8 text-green-500" />
            <div>
              <p className="text-2xl font-bold">
                ${(collective.stats.monthlyRevenue / 1000).toFixed(0)}K
              </p>
              <p className="text-xs text-muted-foreground">Monthly Revenue</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Management Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="flex gap-4 border-b mb-6">
          {['members', 'requests', 'endpoints', 'pricing', 'settings'].map((tab) => (
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
              {tab === 'requests' && collective.pendingRequests.length > 0 && (
                <Badge variant="destructive" className="ml-2 text-xs">
                  {collective.pendingRequests.length}
                </Badge>
              )}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="mt-6">
          {activeTab === 'members' && (
            <div className="space-y-4">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold">Current Members</h3>
                <Button>
                  <Mail className="w-4 h-4 mr-2" />
                  Invite Members
                </Button>
              </div>

              {/* Members Table */}
              <Card>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="border-b">
                      <tr>
                        <th className="text-left p-4 text-sm font-medium">Member</th>
                        <th className="text-left p-4 text-sm font-medium">Role</th>
                        <th className="text-left p-4 text-sm font-medium">Joined</th>
                        <th className="text-left p-4 text-sm font-medium">Endpoints</th>
                        <th className="text-left p-4 text-sm font-medium">Contribution</th>
                        <th className="text-left p-4 text-sm font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {collective.members.map((member) => (
                        <tr key={member.id} className="border-b">
                          <td className="p-4">
                            <div className="flex items-center gap-3">
                              {member.avatarUrl ? (
                                <img
                                  src={member.avatarUrl}
                                  alt={member.displayName}
                                  className="w-8 h-8 rounded-full"
                                />
                              ) : (
                                <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
                                  <Users className="w-4 h-4 text-muted-foreground" />
                                </div>
                              )}
                              <div>
                                <p className="font-medium">{member.displayName}</p>
                                <p className="text-xs text-muted-foreground">@{member.username}</p>
                              </div>
                            </div>
                          </td>
                          <td className="p-4">
                            <Badge variant={member.role === 'owner' ? 'default' : 'secondary'}>
                              {member.role}
                            </Badge>
                          </td>
                          <td className="p-4 text-sm text-muted-foreground">
                            {new Date(member.joinedAt).toLocaleDateString()}
                          </td>
                          <td className="p-4 text-sm">{member.endpointCount}</td>
                          <td className="p-4 text-sm">
                            ${member.contribution ? (member.contribution / 1000).toFixed(1) : 0}K
                          </td>
                          <td className="p-4">
                            {member.role !== 'owner' && (
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => handleRemoveMember(member.id)}
                              >
                                <UserX className="w-4 h-4" />
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          )}

          {activeTab === 'requests' && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold mb-4">
                Pending Join Requests ({collective.pendingRequests.length})
              </h3>

              {collective.pendingRequests.length > 0 ? (
                <div className="space-y-4">
                  {collective.pendingRequests.map((request) => (
                    <Card key={request.id} className="p-6">
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-4">
                          {request.avatarUrl ? (
                            <img
                              src={request.avatarUrl}
                              alt={request.displayName}
                              className="w-12 h-12 rounded-full"
                            />
                          ) : (
                            <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center">
                              <Users className="w-6 h-6 text-muted-foreground" />
                            </div>
                          )}
                          <div>
                            <h4 className="font-semibold">{request.displayName}</h4>
                            <p className="text-sm text-muted-foreground mb-1">@{request.username}</p>
                            {request.institution && (
                              <p className="text-sm text-muted-foreground mb-3">
                                {request.institution}
                              </p>
                            )}
                            <div className="bg-muted/50 rounded p-3 mb-3">
                              <p className="text-sm">{request.message}</p>
                            </div>
                            <p className="text-xs text-muted-foreground flex items-center gap-1">
                              <Calendar className="w-3 h-3" />
                              Requested {new Date(request.requestedAt).toLocaleString()}
                            </p>
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            onClick={() => handleApproveRequest(request.id)}
                          >
                            <UserCheck className="w-4 h-4 mr-1" />
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleRejectRequest(request.id)}
                          >
                            <UserX className="w-4 h-4 mr-1" />
                            Reject
                          </Button>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
              ) : (
                <Card className="p-12 text-center">
                  <Users className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">No pending join requests</p>
                </Card>
              )}
            </div>
          )}

          {activeTab === 'endpoints' && (
            <div className="space-y-4">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold">Collective Endpoints</h3>
                <Button variant="outline">
                  <Database className="w-4 h-4 mr-2" />
                  Bulk Operations
                </Button>
              </div>

              <Card>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="border-b">
                      <tr>
                        <th className="text-left p-4 text-sm font-medium">
                          <input type="checkbox" className="rounded" />
                        </th>
                        <th className="text-left p-4 text-sm font-medium">Endpoint</th>
                        <th className="text-left p-4 text-sm font-medium">Owner</th>
                        <th className="text-left p-4 text-sm font-medium">Type</th>
                        <th className="text-left p-4 text-sm font-medium">Pricing</th>
                        <th className="text-left p-4 text-sm font-medium">Queries</th>
                        <th className="text-left p-4 text-sm font-medium">Revenue</th>
                        <th className="text-left p-4 text-sm font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {collective.endpoints.map((endpoint) => (
                        <tr key={endpoint.id} className="border-b">
                          <td className="p-4">
                            <input type="checkbox" className="rounded" />
                          </td>
                          <td className="p-4">
                            <div>
                              <p className="font-medium">{endpoint.name}</p>
                              <p className="text-xs text-muted-foreground">{endpoint.slug}</p>
                            </div>
                          </td>
                          <td className="p-4 text-sm">@{endpoint.owner}</td>
                          <td className="p-4">
                            <Badge variant="secondary">{endpoint.type}</Badge>
                          </td>
                          <td className="p-4">
                            <Badge
                              variant={endpoint.usesCollectivePricing ? 'default' : 'outline'}
                            >
                              {endpoint.usesCollectivePricing ? 'Collective' : 'Custom'}
                            </Badge>
                          </td>
                          <td className="p-4 text-sm">
                            {(endpoint.queryCount / 1000).toFixed(0)}K
                          </td>
                          <td className="p-4 text-sm">${endpoint.revenue}</td>
                          <td className="p-4">
                            <Button size="sm" variant="ghost">
                              <MoreVertical className="w-4 h-4" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          )}

          {activeTab === 'pricing' && (
            <div className="space-y-6">
              <h3 className="text-lg font-semibold mb-4">Pricing Tiers</h3>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {collective.pricingTiers.map((tier) => (
                  <Card key={tier.id} className={cn("p-6", tier.isDefault && "ring-2 ring-primary")}>
                    {tier.isDefault && (
                      <Badge className="mb-2">Default Tier</Badge>
                    )}
                    <Input
                      value={tier.name}
                      className="font-semibold mb-2"
                      placeholder="Tier Name"
                    />
                    <Textarea
                      value={tier.description}
                      className="text-sm mb-4"
                      placeholder="Description"
                      rows={2}
                    />
                    <div className="flex items-baseline gap-2 mb-2">
                      <Input
                        type="number"
                        value={tier.price}
                        className="w-24 text-2xl font-bold"
                        placeholder="0"
                      />
                      <select className="text-sm border rounded px-2 py-1">
                        <option value="per-call">per call</option>
                        <option value="per-token">per token</option>
                        <option value="per-month">per month</option>
                      </select>
                    </div>
                    <div className="flex items-center gap-2 mt-4">
                      <Switch checked={tier.isDefault} />
                      <Label className="text-sm">Set as default</Label>
                    </div>
                  </Card>
                ))}
              </div>

              <Button>
                <Plus className="w-4 h-4 mr-2" />
                Add Pricing Tier
              </Button>
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="space-y-6">
              <Card className="p-6">
                <h3 className="text-lg font-semibold mb-4">General Settings</h3>
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="name">Collective Name</Label>
                    <Input id="name" value={collective.name} />
                  </div>
                  <div>
                    <Label htmlFor="description">Description</Label>
                    <Textarea id="description" value={collective.description} rows={3} />
                  </div>
                  <div>
                    <Label htmlFor="domain">Custom Domain</Label>
                    <Input id="domain" value={collective.domain} placeholder="collective.example.com" />
                  </div>
                </div>
              </Card>

              <Card className="p-6">
                <h3 className="text-lg font-semibold mb-4">Membership Settings</h3>
                <div className="space-y-4">
                  <div>
                    <Label>Membership Type</Label>
                    <select className="w-full border rounded px-3 py-2 mt-1">
                      <option value="open">Open - Anyone can join</option>
                      <option value="request">Request - Approval required</option>
                      <option value="invite-only">Invite Only - By invitation only</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch />
                    <Label>Require email verification</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch />
                    <Label>Auto-approve requests from verified institutions</Label>
                  </div>
                </div>
              </Card>

              <Card className="p-6">
                <h3 className="text-lg font-semibold mb-4">Capabilities</h3>
                <div className="space-y-3">
                  {Object.entries(collective.capabilities).map(([key, enabled]) => (
                    <div key={key} className="flex items-center gap-2">
                      <Switch checked={enabled} />
                      <Label>
                        {key.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase())}
                      </Label>
                    </div>
                  ))}
                </div>
              </Card>

              <div className="flex justify-end gap-2">
                <Button variant="outline">Cancel</Button>
                <Button>Save Settings</Button>
              </div>
            </div>
          )}
        </div>
      </Tabs>
    </div>
  );
}