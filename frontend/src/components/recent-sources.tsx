import React from 'react';

import { ArrowRight } from 'lucide-react';

interface RecentSource {
  name: string;
  queries: string;
  color: string;
  hoverBorder: string;
}

export function RecentSources() {
  const recentSources: RecentSource[] = [
    {
      name: 'WHO COVID-19 Database',
      queries: '8.7k',
      color: 'bg-[#6976ae]',
      hoverBorder: 'hover:border-l-[#6976ae]'
    },
    {
      name: 'Climate TRACE API',
      queries: '4.2k',
      color: 'bg-[#53bea9]',
      hoverBorder: 'hover:border-l-[#53bea9]'
    },
    {
      name: 'NIH Clinical Trials',
      queries: '12.3k',
      color: 'bg-[#937098]',
      hoverBorder: 'hover:border-l-[#937098]'
    },
    {
      name: 'GenBank Genomics',
      queries: '6.1k',
      color: 'bg-[#52a8c5]',
      hoverBorder: 'hover:border-l-[#52a8c5]'
    }
  ];

  return (
    <div>
      <div className='mb-5 flex items-center justify-between'>
        <div className='flex items-center gap-2'>
          <div className='h-6 w-1 rounded-full bg-gradient-to-b from-[#6976ae] via-[#937098] to-[#52a8c5]'></div>
          <h4 className='font-rubik text-sm tracking-wide text-black uppercase'>Recent Sources</h4>
        </div>
        <a
          href='#'
          className='group flex items-center gap-1 text-xs text-[#6976ae] transition-colors hover:text-[#272532]'
        >
          View all{' '}
          <ArrowRight className='h-3 w-3 transition-transform group-hover:translate-x-0.5' />
        </a>
      </div>
      <div className='space-y-1.5'>
        {recentSources.map((source, index) => (
          <a
            key={index}
            href='#'
            title={`View ${source.name}`}
            className={`group flex items-center gap-3 rounded-lg border-l-2 border-transparent px-4 py-3 transition-all hover:bg-[#f7f6f9] ${source.hoverBorder} hover:shadow-sm`}
          >
            <div className={`h-2 w-2 rounded-full ${source.color} flex-shrink-0`}></div>
            <span className='font-inter flex-1 text-sm text-black transition-colors group-hover:text-black'>
              {source.name}
            </span>
            <span
              className='font-inter rounded-full bg-[#f1f0f4] px-3 py-1 text-xs text-black'
              title={`${source.queries} queries`}
            >
              {source.queries}
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}
