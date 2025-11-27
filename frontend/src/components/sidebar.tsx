import React from 'react';

import { Database, FileText, Globe, MessageSquare, Sparkles, Users } from 'lucide-react';

interface SidebarProperties {
  activeView: 'home' | 'browse' | 'participate' | 'build' | 'datasites';
  onNavigate: (view: 'home' | 'browse' | 'participate' | 'build' | 'datasites') => void;
  onAuthRequired?: () => void;
}

export function Sidebar({ activeView, onNavigate, onAuthRequired }: Readonly<SidebarProperties>) {
  const navItems = [
    {
      id: 'home',
      label: 'Chat',
      icon: MessageSquare,
      action: () => {
        onNavigate('home');
      }
    },
    {
      id: 'browse',
      label: 'Browse',
      icon: Globe,
      action: () => {
        onNavigate('browse');
      }
    },
    {
      id: 'participate',
      label: 'Participate',
      icon: Users,
      action: () => {
        if (onAuthRequired) {
          onAuthRequired();
        } else {
          onNavigate('participate');
        }
      }
    },
    {
      id: 'build',
      label: 'Build',
      icon: FileText,
      action: () => {
        onNavigate('build');
      }
    },
    {
      id: 'datasites',
      label: 'My Data',
      icon: Database,
      action: () => {
        if (onAuthRequired) {
          onAuthRequired();
        } else {
          onNavigate('datasites');
        }
      }
    }
  ];

  return (
    <aside className='fixed top-0 left-0 z-50 flex h-screen w-20 flex-col items-center border-r border-[#ecebef] bg-[#fcfcfd] py-8'>
      {/* Logo at top */}
      <button
        onClick={() => {
          onNavigate('home');
        }}
        className='group mb-12 block transition-opacity hover:opacity-80'
        aria-label='SyftHub Home'
      >
        <div className='flex items-center justify-center'>
          <Sparkles className='h-8 w-8 text-[#6976ae] transition-colors group-hover:text-[#272532]' />
        </div>
      </button>

      {/* Navigation items */}
      <nav className='flex flex-1 flex-col gap-8'>
        {navItems.map((item) => {
          const isActive = item.id === activeView;
          const Icon = item.icon;

          return (
            <button
              key={item.id}
              onClick={item.action}
              className={`group flex w-full flex-col items-center gap-1 transition-colors ${
                isActive ? 'text-[#272532]' : 'text-[#5e5a72] hover:text-[#272532]'
              }`}
              title={item.label}
            >
              <div
                className={`rounded-lg p-2 transition-colors ${
                  isActive ? 'bg-[#f1f0f4]' : 'group-hover:bg-[#f1f0f4]'
                }`}
              >
                <Icon className='h-5 w-5' />
              </div>
              <span className={`font-inter text-[10px] ${isActive ? 'font-semibold' : ''}`}>
                {item.label}
              </span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
