import Users from 'lucide-react/dist/esm/icons/users';
import Database from 'lucide-react/dist/esm/icons/database';
import TrendingUp from 'lucide-react/dist/esm/icons/trending-up';
import DollarSign from 'lucide-react/dist/esm/icons/dollar-sign';

import { Card } from '@/components/ui/card';

interface CollectiveStatsProps {
  stats: {
    collectiveCount: number;
    totalMembers: number;
    totalEndpoints: number;
    totalQueries: number;
    totalRevenue: number;
  };
}

export function CollectiveStats({ stats }: CollectiveStatsProps) {
  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(0)}K`;
    return num.toString();
  };

  const formatRevenue = (amount: number) => {
    if (amount === 0) return '$0';
    if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`;
    if (amount >= 1000) return `$${(amount / 1000).toFixed(0)}K`;
    return `$${amount}`;
  };

  const statItems = [
    {
      icon: Users,
      label: 'Active Collectives',
      value: stats.collectiveCount,
      formatter: formatNumber,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
    },
    {
      icon: Users,
      label: 'Total Members',
      value: stats.totalMembers,
      formatter: formatNumber,
      color: 'text-green-500',
      bgColor: 'bg-green-500/10',
    },
    {
      icon: Database,
      label: 'Shared Endpoints',
      value: stats.totalEndpoints,
      formatter: formatNumber,
      color: 'text-purple-500',
      bgColor: 'bg-purple-500/10',
    },
    {
      icon: TrendingUp,
      label: 'Monthly Queries',
      value: stats.totalQueries,
      formatter: formatNumber,
      color: 'text-orange-500',
      bgColor: 'bg-orange-500/10',
    },
    {
      icon: DollarSign,
      label: 'Monthly Revenue',
      value: stats.totalRevenue,
      formatter: formatRevenue,
      color: 'text-emerald-500',
      bgColor: 'bg-emerald-500/10',
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {statItems.map((item) => {
        const Icon = item.icon;
        return (
          <Card key={item.label} className="p-4">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${item.bgColor}`}>
                <Icon className={`w-4 h-4 ${item.color}`} />
              </div>
              <div>
                <p className="text-2xl font-bold">{item.formatter(item.value)}</p>
                <p className="text-xs text-muted-foreground">{item.label}</p>
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}