import { Suspense } from 'react';

import { LogOut, Settings, User } from 'lucide-react';
import { Link, Outlet } from 'react-router-dom';

import { AuthModals } from '@/components/auth/auth-modals';
import { BalanceIndicator } from '@/components/balance';
import { SettingsModal } from '@/components/settings/settings-modal';
import { Sidebar } from '@/components/sidebar';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { useAuth } from '@/context/auth-context';
import { useModal } from '@/context/modal-context';
import { useSettingsModal } from '@/context/settings-modal-context';

/**
 * MainLayout - The application shell that wraps all routes.
 *
 * Provides:
 * - Sidebar navigation (self-contained with NavLink)
 * - User menu (auth buttons/user info)
 * - Main content area with Suspense for lazy-loaded routes
 * - Authentication modals
 * - Semantic HTML structure for accessibility
 */
export function MainLayout() {
  const { user, logout, isInitializing } = useAuth();
  const { openLogin, openRegister } = useModal();
  const { openSettings } = useSettingsModal();

  // Show full-screen loading while initializing auth
  if (isInitializing) {
    return <LoadingSpinner fullScreen size='lg' message='Loading SyftHub…' />;
  }

  const handleLogout = () => {
    void logout();
  };

  return (
    <div className='bg-background min-h-screen'>
      {/* Skip link for accessibility */}
      <a
        href='#main-content'
        className='focus:text-syft-primary focus:ring-syft-primary sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[60] focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:shadow-lg focus:ring-2 focus:outline-none'
      >
        Skip to main content
      </a>

      {/* Sidebar navigation - self-contained with React Router NavLink */}
      <Sidebar />

      {/* User Menu - Top Right */}
      <div className='fixed top-4 right-4 z-40 flex items-center gap-3'>
        {user ? (
          <>
            {/* Balance Indicator */}
            <BalanceIndicator />

            {/* User Info & Actions */}
            <div className='border-syft-border flex items-center gap-3 rounded-lg border bg-white/95 px-3 py-2 shadow-sm backdrop-blur-sm'>
              <Link
                to='/profile'
                className='flex items-center gap-2 rounded-md p-1 transition-colors hover:bg-gray-100'
              >
                {user.avatar_url ? (
                  <img
                    src={user.avatar_url}
                    alt=''
                    width={24}
                    height={24}
                    className='h-6 w-6 rounded-full'
                  />
                ) : (
                  <div className='bg-syft-primary flex h-6 w-6 items-center justify-center rounded-full'>
                    <User className='h-3 w-3 text-white' aria-hidden='true' />
                  </div>
                )}
                <span className='font-inter text-syft-primary text-sm font-medium'>
                  {user.name || user.email}
                </span>
              </Link>
              <Button
                variant='ghost'
                size='icon'
                onClick={() => {
                  openSettings();
                }}
                className='text-syft-muted hover:text-syft-primary h-6 w-6'
                aria-label='Settings'
              >
                <Settings className='h-3 w-3' />
              </Button>
              <Button
                variant='ghost'
                size='icon'
                onClick={handleLogout}
                className='text-syft-muted hover:text-syft-primary h-6 w-6'
                aria-label='Logout'
              >
                <LogOut className='h-3 w-3' />
              </Button>
            </div>
          </>
        ) : (
          <div className='flex items-center gap-2'>
            <Button variant='ghost' size='sm' onClick={openLogin} className='font-inter'>
              Sign in
            </Button>
            <Button size='sm' onClick={openRegister} className='font-inter'>
              Sign up
            </Button>
          </div>
        )}
      </div>

      {/* Main content with left margin for sidebar */}
      <main id='main-content' className='ml-20'>
        <Suspense
          fallback={
            <div className='flex min-h-[400px] items-center justify-center'>
              <LoadingSpinner size='lg' message='Loading…' />
            </div>
          }
        >
          <Outlet />
        </Suspense>
      </main>

      {/* Authentication Modals */}
      <AuthModals />

      {/* Settings Modal */}
      <SettingsModal />
    </div>
  );
}
