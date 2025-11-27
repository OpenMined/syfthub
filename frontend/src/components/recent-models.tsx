import React from 'react';

import { ArrowRight } from 'lucide-react';

interface RecentModel {
  name: string;
  downloads: string;
  color: string;
  hoverBorder: string;
}

export function RecentModels() {
  const recentModels: RecentModel[] = [
    {
      name: 'FedRAG-Clinical-7B',
      downloads: '15.6k',
      color: 'bg-[#f79763]',
      hoverBorder: 'hover:border-l-[#f79763]'
    },
    {
      name: 'BioMedLM-Federated',
      downloads: '22.1k',
      color: 'bg-[#cc677b]',
      hoverBorder: 'hover:border-l-[#cc677b]'
    },
    {
      name: 'NewsAggregator-GPT',
      downloads: '8.9k',
      color: 'bg-[#6976ae]',
      hoverBorder: 'hover:border-l-[#6976ae]'
    },
    {
      name: 'ClimateQA-Foundation',
      downloads: '31.2k',
      color: 'bg-[#52a8c5]',
      hoverBorder: 'hover:border-l-[#52a8c5]'
    }
  ];

  return (
    <div>
      <div className='mb-5 flex items-center justify-between'>
        <div className='flex items-center gap-2'>
          <div className='h-6 w-1 rounded-full bg-gradient-to-b from-[#f79763] via-[#cc677b] to-[#6976ae]'></div>
          <h4 className='font-rubik text-sm tracking-wide text-black uppercase'>Recent Models</h4>
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
        {recentModels.map((model, index) => (
          <a
            key={index}
            href='#'
            title={`View ${model.name}`}
            className={`group flex items-center gap-3 rounded-lg border-l-2 border-transparent px-4 py-3 transition-all hover:bg-[#f7f6f9] ${model.hoverBorder} hover:shadow-sm`}
          >
            <div className={`h-2 w-2 rounded-full ${model.color} flex-shrink-0`}></div>
            <span className='font-inter flex-1 text-sm text-black transition-colors group-hover:text-black'>
              {model.name}
            </span>
            <span
              className='font-inter rounded-full bg-[#f1f0f4] px-3 py-1 text-xs text-black'
              title={`${model.downloads} downloads`}
            >
              {model.downloads}
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}
