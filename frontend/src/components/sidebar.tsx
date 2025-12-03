import type React from 'react';

import { Database, FileText, Globe, MessageSquare, Sparkles } from 'lucide-react';
import { NavLink } from 'react-router-dom';

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
  { id: 'build', path: '/build', label: 'Build', icon: FileText, protected: false },
  { id: 'endpoints', path: '/endpoints', label: 'Endpoints', icon: Database, protected: true }
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
  const handleProtectedClick = (e: React.MouseEvent) => {
    if (!user) {
      e.preventDefault();
      openLogin();
    }
  };

  return (
    <aside className='border-syft-border bg-syft-background fixed top-0 left-0 z-50 flex h-screen w-20 flex-col items-center border-r py-8'>
      {/* Logo at top */}
      <NavLink
        to='/'
        className='group mb-12 block transition-opacity hover:opacity-80'
        aria-label='SyftHub Home'
      >
        <div className='flex items-center justify-center'>
          <Sparkles className='text-syft-secondary group-hover:text-syft-primary h-8 w-8 transition-colors' />
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
                  isActive ? 'text-syft-primary' : 'text-syft-muted hover:text-syft-primary'
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
                      isActive ? 'bg-syft-surface' : 'group-hover:bg-syft-surface'
                    )}
                  >
                    <Icon className='h-5 w-5' />
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
