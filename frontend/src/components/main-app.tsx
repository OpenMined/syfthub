import React, { useEffect, useState } from 'react';

import { LogOut, User } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';

import { useAuth } from '@/context/auth-context';

import { LoginModal } from './auth/login-modal';
import { RegisterModal } from './auth/register-modal';
import { BrowseView } from './browse-view';
import { BuildView } from './build-view';
import { ChatView } from './chat-view';
import { DatasiteDetail } from './datasite-detail';
import { DatasiteManagement } from './datasite-management';
import { Hero } from './hero';
import { ParticipateView } from './participate-view';
import { ProfileView } from './profile-view';
import { RecentModels } from './recent-models';
import { RecentSources } from './recent-sources';
import { Sidebar } from './sidebar';
import { Button } from './ui/button';
import ThemeToggle from './ui/theme-toggle';

export function MainApp() {
  const { user, logout, isInitializing } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [view, setView] = useState<
    | 'home'
    | 'browse'
    | 'chat'
    | 'participate'
    | 'build'
    | 'profile'
    | 'datasites'
    | 'datasite-detail'
  >('home');
  const [selectedDatasiteSlug, setSelectedDatasiteSlug] = useState<string | null>(null);
  const [selectedDatasiteOwner, setSelectedDatasiteOwner] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<'login' | 'register' | null>(null);

  // Handle URL routing and GitHub-style datasite URLs
  useEffect(() => {
    const path = location.pathname;

    // Handle GitHub-style datasite URLs: /:username/:datasite-name
    const datasiteMatch = /^\/([^/]+)\/([^/]+)$/.exec(path);
    if (datasiteMatch) {
      const username = datasiteMatch[1] ?? '';
      const datasiteName = datasiteMatch[2] ?? '';
      // Check if this looks like a username/datasite pattern (not a special route)
      const specialRoutes = ['browse', 'chat', 'participate', 'build', 'profile', 'datasites'];
      if (username && datasiteName && !specialRoutes.includes(username)) {
        setSelectedDatasiteOwner(username);
        setSelectedDatasiteSlug(datasiteName);
        setView('datasite-detail');
        return;
      }
    }

    // Handle regular routes
    switch (path) {
      case '/': {
        setView('home');

        break;
      }
      case '/browse': {
        setView('browse');

        break;
      }
      case '/chat': {
        setView('chat');

        break;
      }
      case '/participate': {
        setView('participate');

        break;
      }
      case '/build': {
        setView('build');

        break;
      }
      case '/profile': {
        setView('profile');

        break;
      }
      case '/datasites': {
        setView('datasites');

        break;
      }
      default: {
        // Default to home for unknown routes
        setView('home');
      }
    }
  }, [location.pathname]);

  // Show loading screen while initializing
  if (isInitializing) {
    return (
      <div className='flex min-h-screen items-center justify-center bg-[#fcfcfd]'>
        <div className='flex items-center gap-3 text-[#272532]'>
          <div className='h-6 w-6 animate-spin rounded-full border-2 border-[#272532] border-t-transparent'></div>
          <span className='font-inter text-lg'>Loading SyftHub...</span>
        </div>
      </div>
    );
  }

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    navigate('/chat');
  };

  const handleNavigate = (
    target: 'home' | 'browse' | 'participate' | 'build' | 'profile' | 'datasites'
  ) => {
    if (target === 'browse') {
      setSearchQuery('');
    }

    // Navigate using React Router
    const targetPath = target === 'home' ? '/' : `/${target}`;
    navigate(targetPath);

    // Clear datasite selections when navigating away
    setSelectedDatasiteSlug(null);
    setSelectedDatasiteOwner(null);
  };

  const handleViewDatasite = (slug: string, owner = 'anonymous') => {
    // Navigate to GitHub-style URL: /username/datasite-name
    navigate(`/${owner}/${slug}`);
  };

  const handleLogout = () => {
    void logout();
  };

  const openLoginModal = () => {
    setAuthMode('login');
  };
  const openRegisterModal = () => {
    setAuthMode('register');
  };
  const closeAuthModal = () => {
    setAuthMode(null);
  };

  const switchToRegister = () => {
    setAuthMode('register');
  };
  const switchToLogin = () => {
    setAuthMode('login');
  };

  return (
    <div className='bg-background min-h-screen'>
      <Sidebar
        activeView={
          view === 'chat' || view === 'profile' || view === 'datasite-detail' ? 'home' : view
        }
        onNavigate={handleNavigate}
        onAuthRequired={user ? undefined : openLoginModal}
      />

      {/* User Menu - Top Right */}
      <div className='fixed top-4 right-4 z-40 flex items-center gap-3'>
        <ThemeToggle />
        {user ? (
          <div className='flex items-center gap-3 rounded-lg border border-[#ecebef] bg-white/95 px-3 py-2 shadow-sm backdrop-blur-sm'>
            <button
              onClick={() => navigate('/profile')}
              className='flex items-center gap-2 rounded-md p-1 transition-colors hover:bg-gray-100'
            >
              {user.avatar ? (
                <img src={user.avatar} alt={user.name} className='h-6 w-6 rounded-full' />
              ) : (
                <div className='flex h-6 w-6 items-center justify-center rounded-full bg-[#272532]'>
                  <User className='h-3 w-3 text-white' />
                </div>
              )}
              <span className='font-inter text-sm font-medium text-[#272532]'>
                {user.name || user.email}
              </span>
            </button>
            <Button
              variant='ghost'
              size='icon'
              onClick={handleLogout}
              className='h-6 w-6 text-[#5e5a72] hover:text-[#272532]'
            >
              <LogOut className='h-3 w-3' />
            </Button>
          </div>
        ) : (
          <div className='flex items-center gap-2'>
            <Button variant='ghost' size='sm' onClick={openLoginModal} className='font-inter'>
              Sign in
            </Button>
            <Button size='sm' onClick={openRegisterModal} className='font-inter'>
              Sign up
            </Button>
          </div>
        )}
      </div>

      {/* Main content with left margin for sidebar */}
      <div className='ml-20'>
        {view === 'home' && (
          <>
            <Hero onSearch={handleSearch} onAuthRequired={user ? undefined : openLoginModal} />
            <section className='bg-white px-6 py-6'>
              <div className='mx-auto grid max-w-4xl gap-10 md:grid-cols-2'>
                <RecentSources />
                <RecentModels />
              </div>
            </section>
          </>
        )}

        {view === 'browse' && (
          <BrowseView
            initialQuery={searchQuery}
            onAuthRequired={user ? undefined : openLoginModal}
            onViewDatasite={handleViewDatasite}
          />
        )}

        {view === 'chat' && <ChatView initialQuery={searchQuery} />}

        {view === 'participate' && (
          <ParticipateView onAuthRequired={user ? undefined : openLoginModal} />
        )}

        {view === 'build' && <BuildView />}

        {view === 'profile' && <ProfileView />}

        {view === 'datasites' && <DatasiteManagement />}

        {view === 'datasite-detail' && selectedDatasiteSlug && (
          <DatasiteDetail
            slug={selectedDatasiteSlug}
            owner={selectedDatasiteOwner}
            onBack={() => navigate('/browse')}
          />
        )}
      </div>

      {/* Authentication Modals */}
      <LoginModal
        isOpen={authMode === 'login'}
        onClose={closeAuthModal}
        onSwitchToRegister={switchToRegister}
      />

      <RegisterModal
        isOpen={authMode === 'register'}
        onClose={closeAuthModal}
        onSwitchToLogin={switchToLogin}
      />
    </div>
  );
}
