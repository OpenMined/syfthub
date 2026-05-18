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
      <PageHeader title='Collectives' />
      
      <div className="mx-auto max-w-6xl px-6 py-8">
        {/* Simple Hero */}
        <div className="text-center mb-10">
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-6">
            Trusted groups of data owners. Better discovery, shared infrastructure, collective leverage.
          </p>
          <Link to="/collectives/browse">
            <Button size="lg">
              Browse Collectives
            </Button>
          </Link>
        </div>

        {/* Featured Collectives - The most important content */}
        <div className="mb-10">
          <h2 className="text-lg font-semibold mb-4">Active Collectives</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {featuredCollectives.map(collective => (
              <Link key={collective.id} to={`/c/${collective.slug}`}>
                <Card className="p-4 hover:shadow-md transition-shadow h-full">
                  <div className="flex items-start gap-3 mb-2">
                    <img
                      src={collective.avatarUrl}
                      alt={collective.name}
                      className="w-10 h-10 rounded-lg"
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-1">
                        <h3 className="font-medium text-sm">{collective.name}</h3>
                        {collective.verified && (
                          <CheckCircle className="w-3.5 h-3.5 text-green-500" />
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {collective.stats.memberCount} members
                      </p>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground line-clamp-2">
                    {collective.description}
                  </p>
                  <div className="flex gap-2 mt-2">
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
          <div className="text-center mt-4">
            <Link to="/collectives/browse" className="text-sm text-primary hover:underline">
              View all collectives →
            </Link>
          </div>
        </div>

        {/* Why Join - Essential benefits only */}
        <div className="grid md:grid-cols-2 gap-6 mb-10">
          <div>
            <h3 className="font-semibold mb-3">For data buyers</h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li className="flex gap-2">
                <CheckCircle className="w-4 h-4 text-green-500 shrink-0 mt-0.5" />
                <span>Verified data provenance and legal entities to contract with</span>
              </li>
              <li className="flex gap-2">
                <Shield className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
                <span>Standard terms and consistent quality across datasets</span>
              </li>
            </ul>
          </div>
          
          <div>
            <h3 className="font-semibold mb-3">For data owners</h3>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li className="flex gap-2">
                <Users className="w-4 h-4 text-purple-500 shrink-0 mt-0.5" />
                <span>Get discovered through collective marketing and endpoints</span>
              </li>
              <li className="flex gap-2">
                <Zap className="w-4 h-4 text-yellow-500 shrink-0 mt-0.5" />
                <span>Share infrastructure costs and negotiate better terms</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Create Section - At the bottom, not competing */}
        <div className="border-t pt-8">
          <div className="text-center">
            <h3 className="text-lg font-semibold mb-2">
              Have an organization with data-owning members?
            </h3>
            <p className="text-sm text-muted-foreground mb-4 max-w-xl mx-auto">
              Create a collective to help your members monetize their data while maintaining control.
            </p>
            <div className="flex gap-3 justify-center">
              <Link to="/collectives/create">
                <Button variant="outline">
                  Create Collective
                </Button>
              </Link>
              <Link to="/contact" className="text-sm text-primary hover:underline flex items-center mt-2">
                Talk to us first
                <ArrowRight className="w-3 h-3 ml-1" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}