import { useCallback } from 'react';

import FileText from 'lucide-react/dist/esm/icons/file-text';
import Globe from 'lucide-react/dist/esm/icons/globe';
import Info from 'lucide-react/dist/esm/icons/info';
import MessageSquare from 'lucide-react/dist/esm/icons/message-square';
import UserPlus from 'lucide-react/dist/esm/icons/user-plus';
import { NavLink } from 'react-router-dom';

import { OpenMinedIcon } from '@/components/ui/openmined-icon';
import { useAuth } from '@/context/auth-context';
import { useModal } from '@/context/modal-context';
import { cn } from '@/lib/utils';

interface NavItem {
  id: string;
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  protected: boolean;
}

const navItems: NavItem[] = [
  { id: 'home', path: '/', label: 'Chat', icon: MessageSquare, protected: false },
  { id: 'browse', path: '/browse', label: 'Browse', icon: Globe, protected: false },
  { id: 'endpoints', path: '/endpoints', label: 'Participate', icon: UserPlus, protected: true },
  { id: 'build', path: '/build', label: 'Build', icon: FileText, protected: false },
  { id: 'about', path: '/about', label: 'About', icon: Info, protected: false }
];

/**
 * Sidebar - Main navigation component.
 *
 * Uses React Router's NavLink for navigation with automatic active state.
 * Protected routes (participate, endpoints) require authentication -
 * clicking them when not logged in opens the login modal.
 */
export function Sidebar() {
  const { user } = useAuth();
  const { openLogin } = useModal();

  /**
   * Handler for protected navigation items.
   * If user is not authenticated, prevents navigation and opens login modal.
   */
  const handleProtectedClick = useCallback(
    (e: React.MouseEvent) => {
      if (!user) {
        e.preventDefault();
        openLogin();
      }
    },
    [user, openLogin]
  );

  return (
    <aside className='border-border bg-background fixed top-0 left-0 z-50 flex h-screen w-20 flex-col items-center border-r py-8'>
      {/* Logo at top */}
      <NavLink
        to='/'
        className='group mb-12 block transition-opacity hover:opacity-80'
        aria-label='SyftHub Home'
      >
        <div className='flex items-center justify-center'>
          <OpenMinedIcon className='h-8 w-8' />
        </div>
      </NavLink>

      {/* Navigation items */}
      <nav className='flex flex-1 flex-col gap-8' aria-label='Main navigation'>
        {navItems.map((item) => {
          const Icon = item.icon;

          return (
            <NavLink
              key={item.id}
              to={item.path}
              onClick={item.protected ? handleProtectedClick : undefined}
              className={({ isActive }) =>
                cn(
                  'group flex w-full flex-col items-center gap-1 transition-colors',
                  isActive ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
                )
              }
              title={item.label}
              end={item.path === '/'}
            >
              {({ isActive }) => (
                <>
                  <div
                    className={cn(
                      'rounded-lg p-2 transition-colors',
                      isActive ? 'bg-muted' : 'group-hover:bg-muted'
                    )}
                  >
                    <Icon className='h-5 w-5' aria-hidden='true' />
                  </div>
                  <span className={cn('font-inter text-[10px]', isActive && 'font-semibold')}>
                    {item.label}
                  </span>
                </>
              )}
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
