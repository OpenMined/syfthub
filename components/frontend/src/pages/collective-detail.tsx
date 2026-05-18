import { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import ArrowLeft from 'lucide-react/dist/esm/icons/arrow-left';
import Shield from 'lucide-react/dist/esm/icons/shield';
import CheckCircle from 'lucide-react/dist/esm/icons/check-circle';
import Users from 'lucide-react/dist/esm/icons/users';
import Database from 'lucide-react/dist/esm/icons/database';
import Copy from 'lucide-react/dist/esm/icons/copy';
import ExternalLink from 'lucide-react/dist/esm/icons/external-link';
import Settings from 'lucide-react/dist/esm/icons/settings';
import UserPlus from 'lucide-react/dist/esm/icons/user-plus';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Modal } from '@/components/ui/modal';
import { Textarea } from '@/components/ui/textarea';
import { useAuth } from '@/context/auth-context';
import { getCollectiveBySlug, currentUserCollectives } from '@/lib/mock-data/collectives';
import { cn } from '@/lib/utils';

export default function CollectiveDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('members');
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
    console.log('Join request submitted:', joinMessage);
    setShowJoinModal(false);
    setJoinMessage('');
  };

  const copyUnifiedEndpoint = () => {
    const endpoint = `https://syftbox.openmined.org/c/${collective.slug}/query`;
    navigator.clipboard.writeText(endpoint);
  };

  return (
    <div className='bg-background min-h-screen'>
      {/* Header Section - Similar to endpoint detail */}
      <div className='border-border bg-card sticky top-0 z-10 border-b backdrop-blur-sm'>
        <div className='mx-auto max-w-5xl px-6 py-4'>
          {/* Back Button */}
          <Button
            variant='ghost'
            size='sm'
            onClick={() => navigate('/collectives/browse')}
            className='mb-4 -ml-2'
          >
            <ArrowLeft className='mr-2 h-4 w-4' />
            Back to Collectives
          </Button>

          {/* Title and Description */}
          <div className='mb-4'>
            <div className='flex items-center gap-3 mb-2'>
              <h1 className='text-2xl font-bold'>{collective.name}</h1>
              {collective.verified && (
                <CheckCircle className='w-5 h-5 text-green-500' aria-label='Verified' />
              )}
            </div>
            <p className='text-muted-foreground'>{collective.description}</p>
          </div>

          {/* Tags */}
          <div className='mb-4 flex flex-wrap gap-2'>
            {collective.tags.map(tag => (
              <Badge key={tag} variant='secondary'>
                {tag}
              </Badge>
            ))}
            <Badge variant='outline'>
              {collective.membershipVisibility === 'open' ? 'Open' : 
               collective.membershipVisibility === 'request' ? 'Request to Join' : 'Invite Only'}
            </Badge>
            {collective.hasLegalEntity && (
              <Badge variant='outline' className='gap-1'>
                <Shield className='w-3 h-3' />
                Legal Entity
              </Badge>
            )}
          </div>

          {/* Admin Button Only */}
          {isAdmin && (
            <div className='flex gap-2'>
              <Link to={`/c/${collective.slug}/admin`}>
                <Button variant='outline' size='sm'>
                  <Settings className='w-4 h-4 mr-2' />
                  Manage
                </Button>
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* Main Content - Similar spacing to endpoint detail */}
      <div className='mx-auto max-w-5xl px-6 py-8'>
        <div className='grid gap-8 lg:grid-cols-3'>
          {/* Left Column - Main Content */}
          <div className='space-y-6 lg:col-span-2'>
            {/* About Card */}
            <Card className='border-border bg-card rounded-xl border p-6'>
              <h2 className='text-lg font-semibold mb-4'>About</h2>
              <div className='prose prose-sm text-muted-foreground'>
                <p className='mb-3'>
                  {collective.name} brings together {collective.stats.memberCount} organizations and researchers working in 
                  {collective.tags[0] === 'healthcare' && ' medical and clinical research, sharing valuable datasets to accelerate breakthrough discoveries in genomics, drug development, and personalized medicine.'}
                  {collective.tags[0] === 'climate' && ' environmental monitoring and climate science, providing real-time Earth observation data to support climate research and policy decisions.'}
                  {collective.tags[0] === 'finance' && ' financial technology and market analysis, enabling secure sharing of market data and risk models while maintaining regulatory compliance.'}
                  {collective.tags[0] === 'research' && ' open science initiatives, promoting reproducible research and data sharing across multiple scientific disciplines.'}
                </p>
                <p className='mb-3'>
                  Members benefit from shared infrastructure costs, unified data discovery, and collective leverage when 
                  negotiating with AI companies and data consumers. 
                  {collective.governance === 'democratic' && ' The collective operates democratically with equal voting rights for all members on key decisions.'}
                  {collective.governance === 'representative' && ' Governance is managed through elected representatives who make decisions on behalf of the membership.'}
                  {collective.governance === 'corporate' && ' The collective operates under a corporate structure with professional management.'}
                </p>
                {collective.hasLegalEntity && (
                  <p>
                    As a registered legal entity, {collective.name} can enter into contracts on behalf of its members, 
                    providing liability protection and professional dispute resolution.
                  </p>
                )}
              </div>
            </Card>

            {/* Tabs for Members/Endpoints */}
            <Card className='border-border bg-card rounded-xl border p-6'>
              <div className='flex gap-4 border-b mb-4'>
                {['members', 'endpoints'].map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={cn(
                      "px-1 py-2 text-sm font-medium capitalize transition-colors",
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
              <div className='mt-2'>
                {activeTab === 'members' && (
                  <div className='space-y-3'>
                    {collective.members.slice(0, 5).map((member) => (
                      <Link
                        key={member.id}
                        to={`/${member.username}`}
                        className='block'
                      >
                        <Card className='p-3 hover:shadow-sm hover:border-primary/30 transition-all cursor-pointer'>
                          <div className='flex items-center justify-between'>
                            <div className='flex items-center gap-3'>
                              {member.avatarUrl ? (
                                <img
                                  src={member.avatarUrl}
                                  alt={member.displayName}
                                  className='w-8 h-8 rounded-full'
                                />
                              ) : (
                                <div className='w-8 h-8 rounded-full bg-muted flex items-center justify-center'>
                                  <Users className='w-4 h-4 text-muted-foreground' />
                                </div>
                              )}
                              <div>
                                <p className='text-sm font-medium hover:text-primary transition-colors'>
                                  {member.displayName}
                                </p>
                                <p className='text-xs text-muted-foreground'>@{member.username}</p>
                              </div>
                            </div>
                            <div className='flex items-center gap-2'>
                              <span className='text-xs text-muted-foreground'>
                                {member.endpointCount} {member.endpointCount === 1 ? 'endpoint' : 'endpoints'}
                              </span>
                              {member.role !== 'member' && (
                                <Badge variant='secondary' className='text-xs'>
                                  {member.role}
                                </Badge>
                              )}
                            </div>
                          </div>
                        </Card>
                      </Link>
                    ))}
                    {collective.members.length > 5 && (
                      <div className='text-sm text-muted-foreground text-center pt-2'>
                        +{collective.members.length - 5} more members
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'endpoints' && (
                  <div className='space-y-3'>
                    {collective.endpoints.slice(0, 5).map((endpoint) => (
                      <Link 
                        key={endpoint.id} 
                        to={`/${endpoint.owner}/${endpoint.slug}`}
                        className='block'
                      >
                        <Card className='p-3 hover:shadow-sm hover:border-primary/30 transition-all cursor-pointer'>
                          <div className='flex items-start justify-between'>
                            <div className='flex-1'>
                              <h4 className='text-sm font-medium hover:text-primary transition-colors'>
                                {endpoint.name}
                              </h4>
                              <p className='text-xs text-muted-foreground mt-1 line-clamp-2'>
                                {endpoint.description}
                              </p>
                              <p className='text-xs text-muted-foreground mt-1'>by @{endpoint.owner}</p>
                            </div>
                            <Badge variant='outline' className='text-xs ml-3'>
                              {endpoint.type === 'dataset' || endpoint.type === 'api' ? 'data' : 'model'}
                            </Badge>
                          </div>
                        </Card>
                      </Link>
                    ))}
                    {collective.endpoints.length > 5 && (
                      <div className='text-sm text-muted-foreground text-center pt-2'>
                        +{collective.endpoints.length - 5} more endpoints
                      </div>
                    )}
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* Right Column - Sidebar */}
          <div className='space-y-6'>
            {/* Join/Member Status */}
            {!userMembership && (
              <Button className='w-full' onClick={() => setShowJoinModal(true)}>
                <UserPlus className='w-4 h-4 mr-2' />
                {collective.membershipVisibility === 'open' ? 'Join Collective' : 'Request to Join'}
              </Button>
            )}
            {userMembership && !isAdmin && (
              <Badge variant='default' className='py-2 px-4 w-full justify-center'>
                <Users className='w-4 h-4 mr-2' />
                Member
              </Badge>
            )}

            {/* Stats Card */}
            <Card className='border-border bg-card rounded-xl border p-6'>
              <div className='space-y-4'>
                <button
                  onClick={() => setActiveTab('members')}
                  className='w-full text-left hover:opacity-80 transition-opacity'
                >
                  <div className='flex items-center gap-2 text-sm text-muted-foreground mb-1'>
                    <Users className='w-4 h-4' />
                    Members
                  </div>
                  <div className='text-2xl font-semibold'>{collective.stats.memberCount}</div>
                </button>
                <button
                  onClick={() => setActiveTab('endpoints')}
                  className='w-full text-left hover:opacity-80 transition-opacity'
                >
                  <div className='flex items-center gap-2 text-sm text-muted-foreground mb-1'>
                    <Database className='w-4 h-4' />
                    Endpoints
                  </div>
                  <div className='text-2xl font-semibold'>{collective.stats.endpointCount}</div>
                </button>
              </div>
            </Card>

            {/* Shared Endpoint Card */}
            <Card className='border-border bg-card rounded-xl border p-6'>
              <h3 className='font-medium mb-3'>Shared Endpoint</h3>
              <p className='text-xs text-muted-foreground mb-4'>
                Query all {collective.stats.endpointCount} endpoints through a single API
              </p>
              <div className='space-y-3'>
                <div className='flex items-center gap-2'>
                  <code className='flex-1 truncate rounded-lg px-2.5 py-1.5 font-mono text-xs bg-muted text-muted-foreground'>
                    https://syftbox.openmined.org/c/{collective.slug}/query
                  </code>
                  <Button
                    variant='ghost'
                    size='sm'
                    onClick={copyUnifiedEndpoint}
                    className='h-7 w-7 shrink-0 p-0 text-muted-foreground hover:text-foreground'
                    title='Copy endpoint'
                  >
                    <Copy className='h-3.5 w-3.5' />
                  </Button>
                </div>
                <div className='flex items-center justify-between text-xs'>
                  <span className='text-muted-foreground'>Estimated cost:</span>
                  <span className='font-medium'>
                    {collective.pricingTiers && collective.pricingTiers[0] 
                      ? collective.pricingTiers[0].price === 0 
                        ? 'Free' 
                        : `$${collective.pricingTiers[0].price}/call`
                      : '$0.001/call'}
                  </span>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>

      {/* Join Request Modal */}
      <Modal
        isOpen={showJoinModal}
        onClose={() => setShowJoinModal(false)}
        title={`Request to Join ${collective.name}`}
      >
        <div className='space-y-4'>
          <p className='text-sm text-muted-foreground'>
            Tell the collective administrators why you'd like to join and how you can contribute.
          </p>
          <Textarea
            placeholder='I would like to join because...'
            value={joinMessage}
            onChange={(e) => setJoinMessage(e.target.value)}
            rows={4}
          />
          <div className='flex justify-end gap-2'>
            <Button variant='outline' onClick={() => setShowJoinModal(false)}>
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