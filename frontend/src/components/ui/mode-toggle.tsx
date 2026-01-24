import Laptop from 'lucide-react/dist/esm/icons/laptop';
import Moon from 'lucide-react/dist/esm/icons/moon';
import Sun from 'lucide-react/dist/esm/icons/sun';

import { useTheme } from '@/context/theme-context';

import { Button } from './button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger
} from './dropdown-menu';

/**
 * ModeToggle - Theme switcher component with dropdown menu.
 *
 * Displays the current theme icon (Sun for light, Moon for dark) and provides
 * a dropdown to switch between Light, Dark, and System themes.
 */
export function ModeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant='ghost' size='icon' className='h-8 w-8' aria-label='Toggle theme'>
          <Sun
            className='h-4 w-4 scale-100 rotate-0 transition-all dark:scale-0 dark:rotate-90'
            aria-hidden='true'
          />
          <Moon
            className='absolute h-4 w-4 scale-0 rotate-90 transition-all dark:scale-100 dark:rotate-0'
            aria-hidden='true'
          />
          <span className='sr-only'>Toggle theme</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end'>
        <DropdownMenuItem
          onClick={() => {
            setTheme('light');
          }}
          className={theme === 'light' ? 'bg-accent' : ''}
        >
          <Sun className='mr-2 h-4 w-4' aria-hidden='true' />
          <span>Light</span>
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => {
            setTheme('dark');
          }}
          className={theme === 'dark' ? 'bg-accent' : ''}
        >
          <Moon className='mr-2 h-4 w-4' aria-hidden='true' />
          <span>Dark</span>
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => {
            setTheme('system');
          }}
          className={theme === 'system' ? 'bg-accent' : ''}
        >
          <Laptop className='mr-2 h-4 w-4' aria-hidden='true' />
          <span>System</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
