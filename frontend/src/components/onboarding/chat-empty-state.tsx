import { motion } from 'framer-motion';
import Database from 'lucide-react/dist/esm/icons/database';
import Search from 'lucide-react/dist/esm/icons/search';
import Send from 'lucide-react/dist/esm/icons/send';
import Shield from 'lucide-react/dist/esm/icons/shield';

import { cn } from '@/lib/utils';

const SUGGESTIONS = [
  {
    label: 'What datasets are available?',
    icon: Database
  },
  {
    label: 'Search for health statistics in the US',
    icon: Search
  },
  {
    label: 'Find population data by country',
    icon: Search
  },
  {
    label: 'How does privacy-preserving querying work?',
    icon: Shield
  }
];

const STEPS = [
  { number: '1', title: 'Ask a question', description: 'Type any query in the input below.' },
  {
    number: '2',
    title: 'Sources are matched',
    description: 'SyftHub finds the best data sources for your query.'
  },
  {
    number: '3',
    title: 'Get your answer',
    description: 'Results are aggregated and returned to you privately.'
  }
];

interface ChatEmptyStateProperties {
  onSuggestionClick: (query: string) => void;
}

export function ChatEmptyState({ onSuggestionClick }: Readonly<ChatEmptyStateProperties>) {
  return (
    <div className='flex flex-col items-center justify-center px-4 py-12'>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className='w-full max-w-2xl space-y-10'
      >
        {/* Heading */}
        <div className='text-center'>
          <h2 className='font-rubik text-foreground text-2xl font-semibold'>Ask Anything</h2>
          <p className='font-inter text-muted-foreground mt-2 text-sm'>
            Query multiple privacy-preserving data sources with a single question.
          </p>
        </div>

        {/* Suggestion Cards - 2x2 grid */}
        <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
          {SUGGESTIONS.map((suggestion, index) => {
            const Icon = suggestion.icon;
            return (
              <motion.button
                key={suggestion.label}
                type='button'
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 + index * 0.05, duration: 0.25 }}
                onClick={() => {
                  onSuggestionClick(suggestion.label);
                }}
                className={cn(
                  'group flex items-start gap-3 rounded-xl border p-4 text-left transition-colors',
                  'border-border bg-muted/40 hover:bg-muted hover:border-input',
                  'dark:bg-muted/20 dark:hover:bg-muted/40',
                  'focus:ring-ring/20 focus:ring-2 focus:outline-none'
                )}
              >
                <div className='bg-primary/10 group-hover:bg-primary/20 mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors'>
                  <Icon className='text-primary h-4 w-4' aria-hidden='true' />
                </div>
                <div className='flex items-center gap-2'>
                  <span className='font-inter text-foreground text-sm leading-snug'>
                    {suggestion.label}
                  </span>
                  <Send
                    className='text-muted-foreground h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100'
                    aria-hidden='true'
                  />
                </div>
              </motion.button>
            );
          })}
        </div>

        {/* How it works */}
        <div className='space-y-4'>
          <h3 className='font-rubik text-muted-foreground text-center text-xs font-medium tracking-wide uppercase'>
            How it works
          </h3>
          <div className='grid grid-cols-1 gap-4 sm:grid-cols-3'>
            {STEPS.map((step) => (
              <div key={step.number} className='flex flex-col items-center text-center'>
                <div className='bg-primary text-primary-foreground font-rubik mb-2 flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold'>
                  {step.number}
                </div>
                <span className='font-rubik text-foreground text-sm font-medium'>{step.title}</span>
                <span className='font-inter text-muted-foreground mt-1 text-xs leading-relaxed'>
                  {step.description}
                </span>
              </div>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
