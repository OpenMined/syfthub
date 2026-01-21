import React from 'react';

import type { SettingsTab } from '@/context/settings-modal-context';

import { AnimatePresence, motion } from 'framer-motion';
import AlertTriangle from 'lucide-react/dist/esm/icons/alert-triangle';
import CreditCard from 'lucide-react/dist/esm/icons/credit-card';
import Lock from 'lucide-react/dist/esm/icons/lock';
import User from 'lucide-react/dist/esm/icons/user';
import X from 'lucide-react/dist/esm/icons/x';

import { Button } from '@/components/ui/button';
import { useSettingsModal } from '@/context/settings-modal-context';
import { cn } from '@/lib/utils';

import { DangerZoneTab } from './danger-zone-tab';
import { PaymentSettingsTab } from './payment-settings-tab';
import { ProfileSettingsTab } from './profile-settings-tab';
import { SecuritySettingsTab } from './security-settings-tab';

interface TabItem {
  id: SettingsTab;
  label: string;
  icon: React.ReactNode;
  danger?: boolean;
}

const TABS: TabItem[] = [
  { id: 'profile', label: 'Profile', icon: <User className='h-4 w-4' aria-hidden='true' /> },
  { id: 'security', label: 'Security', icon: <Lock className='h-4 w-4' aria-hidden='true' /> },
  { id: 'payment', label: 'Payment', icon: <CreditCard className='h-4 w-4' aria-hidden='true' /> },
  {
    id: 'danger-zone',
    label: 'Danger Zone',
    icon: <AlertTriangle className='h-4 w-4' aria-hidden='true' />,
    danger: true
  }
];

// Selector for focusable elements
const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]):not([disabled])';

export function SettingsModal() {
  const { isOpen, closeSettings, activeTab, setActiveTab } = useSettingsModal();
  const modalReference = React.useRef<HTMLDivElement>(null);
  const previousActiveElement = React.useRef<Element | null>(null);

  // Handle focus management
  React.useEffect(() => {
    if (isOpen) {
      previousActiveElement.current = document.activeElement;
      const timeoutId = setTimeout(() => {
        const focusableElements = modalReference.current?.querySelectorAll(FOCUSABLE_SELECTOR);
        if (focusableElements && focusableElements.length > 0) {
          (focusableElements[0] as HTMLElement).focus();
        }
      }, 50);
      return () => {
        clearTimeout(timeoutId);
      };
    } else if (previousActiveElement.current instanceof HTMLElement) {
      previousActiveElement.current.focus();
    }
  }, [isOpen]);

  // Handle escape key and body scroll
  React.useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen) {
        closeSettings();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, closeSettings]);

  // Handle Tab key for focus trapping
  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key !== 'Tab') return;

    const nodeList = modalReference.current?.querySelectorAll(FOCUSABLE_SELECTOR);
    if (!nodeList || nodeList.length === 0) return;

    const focusableElements = [...nodeList] as HTMLElement[];
    const firstElement = focusableElements[0];
    const lastElement = focusableElements.at(-1);
    if (!firstElement || !lastElement) return;

    if (event.shiftKey && document.activeElement === (firstElement as Element)) {
      event.preventDefault();
      lastElement.focus();
    } else if (!event.shiftKey && document.activeElement === (lastElement as Element)) {
      event.preventDefault();
      firstElement.focus();
    }
  };

  const handleOverlayClick = (event: React.MouseEvent) => {
    if (event.target === event.currentTarget) {
      closeSettings();
    }
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'profile': {
        return <ProfileSettingsTab />;
      }
      case 'security': {
        return <SecuritySettingsTab />;
      }
      case 'payment': {
        return <PaymentSettingsTab />;
      }
      case 'danger-zone': {
        return <DangerZoneTab />;
      }
      default: {
        return <ProfileSettingsTab />;
      }
    }
  };

  return (
    <AnimatePresence>
      {isOpen ? (
        <div
          className='fixed inset-0 z-50 flex items-center justify-center p-4'
          onKeyDown={handleKeyDown}
        >
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className='absolute inset-0 bg-black/50 backdrop-blur-sm'
            onClick={handleOverlayClick}
          />

          {/* Modal Content */}
          <motion.div
            ref={modalReference}
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', duration: 0.3 }}
            className='border-syft-border relative flex h-[600px] w-full max-w-3xl overflow-hidden rounded-xl border bg-white shadow-xl'
            role='dialog'
            aria-modal='true'
            aria-labelledby='settings-modal-title'
          >
            {/* Sidebar */}
            <div className='flex w-48 flex-col border-r border-gray-200 bg-gray-50'>
              <div className='border-b border-gray-200 p-4'>
                <h2
                  id='settings-modal-title'
                  className='font-rubik text-lg font-semibold text-gray-900'
                >
                  Settings
                </h2>
              </div>
              <nav className='flex-1 space-y-1 p-2'>
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => {
                      setActiveTab(tab.id);
                    }}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors',
                      (() => {
                        if (activeTab === tab.id) {
                          return tab.danger
                            ? 'bg-red-100 text-red-700'
                            : 'bg-blue-100 text-blue-700';
                        }
                        return tab.danger
                          ? 'text-red-600 hover:bg-red-50'
                          : 'text-gray-700 hover:bg-gray-100';
                      })()
                    )}
                  >
                    {tab.icon}
                    {tab.label}
                  </button>
                ))}
              </nav>
            </div>

            {/* Content Area */}
            <div className='flex flex-1 flex-col'>
              {/* Close Button */}
              <Button
                variant='ghost'
                size='icon'
                className='text-syft-muted hover:text-syft-primary absolute top-3 right-3 z-10 h-8 w-8'
                onClick={closeSettings}
                aria-label='Close settings'
              >
                <X className='h-4 w-4' aria-hidden='true' />
              </Button>

              {/* Tab Content */}
              <div className='flex-1 overflow-y-auto p-6'>{renderTabContent()}</div>
            </div>
          </motion.div>
        </div>
      ) : null}
    </AnimatePresence>
  );
}
