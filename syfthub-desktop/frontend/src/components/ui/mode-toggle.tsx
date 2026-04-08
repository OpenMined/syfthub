import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

type Theme = 'light' | 'dark' | 'system';

const CYCLE: Theme[] = ['light', 'dark', 'system'];

const ICONS = {
  light: <Sun className='h-4 w-4' />,
  dark: <Moon className='h-4 w-4' />,
  system: <Monitor className='h-4 w-4' />,
};

const LABELS: Record<Theme, string> = {
  light: 'Light theme',
  dark: 'Dark theme',
  system: 'System theme',
};

export function ModeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();

  const handleClick = () => {
    const currentIndex = CYCLE.indexOf(theme);
    const nextIndex = (currentIndex + 1) % CYCLE.length;
    setTheme(CYCLE[nextIndex]);
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant='ghost'
          size='icon'
          onClick={handleClick}
          aria-label={`Switch theme (current: ${theme})`}
          className={className}
        >
          {ICONS[theme]}
        </Button>
      </TooltipTrigger>
      <TooltipContent side='top'>
        <p>{LABELS[theme]}</p>
      </TooltipContent>
    </Tooltip>
  );
}
