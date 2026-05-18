import { Link } from 'react-router-dom';
import { 
  CheckCircle,
  Users,
  ArrowRight,
  Shield,
  Zap
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { PageHeader } from '@/components/ui/page-header';
import { mockCollectives } from '@/lib/mock-data/collectives';

export default function CollectivesPage() {
  // Get featured collectives (first 3 verified ones)
  const featuredCollectives = mockCollectives
    .filter(c => c.verified)
    .slice(0, 3);

  return (
    <>
      <PageHeader title='Collectives' path='~/collectives' />
      
      <div className="mx-auto max-w-6xl px-6 py-6">
        {/* Hero Section */}
        <div className="mb-12">
          <p className="text-lg text-muted-foreground mb-6">
            Trusted groups of data owners. Better discovery, shared infrastructure, collective leverage.
          </p>
          <Link to="/collectives/browse">
            <Button size="lg" className="px-8">
              Browse Collectives
            </Button>
          </Link>
        </div>

        {/* Featured Collectives - Visual Focus */}
        <div className="mb-12">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-semibold">Active Collectives</h2>
            <Link to="/collectives/browse" className="text-sm text-muted-foreground hover:text-primary transition-colors">
              View all →
            </Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {featuredCollectives.map(collective => (
              <Link key={collective.id} to={`/c/${collective.slug}`}>
                <Card className="p-5 hover:shadow-lg hover:border-primary/30 transition-all h-full">
                  <div className="flex items-start gap-3 mb-3">
                    <img
                      src={collective.avatarUrl}
                      alt={collective.name}
                      className="w-12 h-12 rounded-lg"
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-1.5">
                        <h3 className="font-semibold text-sm">{collective.name}</h3>
                        {collective.verified && (
                          <CheckCircle className="w-4 h-4 text-green-500" />
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {collective.stats.memberCount} members • {collective.stats.endpointCount} endpoints
                      </p>
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
                    {collective.description}
                  </p>
                  <div className="flex gap-2">
                    {collective.tags.slice(0, 2).map(tag => (
                      <Badge key={tag} variant="secondary" className="text-xs">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        </div>

        {/* Benefits Section */}
        <div className="bg-muted/30 rounded-xl p-8 mb-12">
          <div className="grid md:grid-cols-2 gap-8">
            <div>
              <h3 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground mb-4">
                For Data Buyers
              </h3>
              <ul className="space-y-3">
                <li className="flex gap-3">
                  <CheckCircle className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
                  <span className="text-sm">Verified data provenance and legal entities to contract with</span>
                </li>
                <li className="flex gap-3">
                  <Shield className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
                  <span className="text-sm">Standard terms and consistent quality across datasets</span>
                </li>
              </ul>
            </div>
            
            <div>
              <h3 className="font-semibold text-sm uppercase tracking-wide text-muted-foreground mb-4">
                For Data Owners
              </h3>
              <ul className="space-y-3">
                <li className="flex gap-3">
                  <Users className="w-4 h-4 text-purple-500 shrink-0 mt-0.5" />
                  <span className="text-sm">Get discovered through collective marketing and endpoints</span>
                </li>
                <li className="flex gap-3">
                  <Zap className="w-4 h-4 text-yellow-500 shrink-0 mt-0.5" />
                  <span className="text-sm">Share infrastructure costs and negotiate better terms</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Create Section - Clean CTA */}
        <div className="text-center py-12 border-t">
          <h3 className="text-lg font-semibold mb-3">
            Running an organization with data-owning members?
          </h3>
          <p className="text-sm text-muted-foreground mb-6 max-w-xl mx-auto">
            Create a collective to help your members monetize their data while maintaining control and privacy.
          </p>
          <div className="flex items-center gap-4 justify-center">
            <Link to="/collectives/create">
              <Button variant="outline" size="lg">
                Create Collective
              </Button>
            </Link>
            <span className="text-muted-foreground">or</span>
            <Link to="/contact" className="text-sm text-primary hover:underline">
              Talk to us first →
            </Link>
          </div>
        </div>
      </div>
    </>
  );
}