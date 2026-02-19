import React from 'react';

import type { SettingsTab } from '@/stores/settings-modal-store';

import { AnimatePresence, motion } from 'framer-motion';
import AlertTriangle from 'lucide-react/dist/esm/icons/alert-triangle';
import CreditCard from 'lucide-react/dist/esm/icons/credit-card';
import Lock from 'lucide-react/dist/esm/icons/lock';
import Server from 'lucide-react/dist/esm/icons/server';
import User from 'lucide-react/dist/esm/icons/user';
import X from 'lucide-react/dist/esm/icons/x';
import { Dialog } from 'radix-ui';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useSettingsModalStore } from '@/stores/settings-modal-store';

import { AggregatorSettingsTab } from './aggregator-settings-tab';
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
  {
    id: 'payment',
    label: 'Payment',
    icon: <CreditCard className='h-4 w-4' aria-hidden='true' />
  },
  {
    id: 'aggregator',
    label: 'Aggregator',
    icon: <Server className='h-4 w-4' aria-hidden='true' />
  },
  {
    id: 'danger-zone',
    label: 'Danger Zone',
    icon: <AlertTriangle className='h-4 w-4' aria-hidden='true' />,
    danger: true
  }
];

const TAB_CONTENT: Record<SettingsTab, React.ComponentType> = {
  profile: ProfileSettingsTab,
  security: SecuritySettingsTab,
  payment: PaymentSettingsTab,
  aggregator: AggregatorSettingsTab,
  'danger-zone': DangerZoneTab
};

export function SettingsModal() {
  const { isOpen, closeSettings, activeTab, setActiveTab } = useSettingsModalStore();
  const tabListReference = React.useRef<HTMLDivElement>(null);

  const handleTabKeyDown = (event: React.KeyboardEvent) => {
    const tabIds = TABS.map((t) => t.id);
    const currentIndex = tabIds.indexOf(activeTab);

    let nextIndex: number | null = null;

    switch (event.key) {
      case 'ArrowDown': {
        nextIndex = (currentIndex + 1) % tabIds.length;
        break;
      }
      case 'ArrowUp': {
        nextIndex = (currentIndex - 1 + tabIds.length) % tabIds.length;
        break;
      }
      case 'Home': {
        nextIndex = 0;
        break;
      }
      case 'End': {
        nextIndex = tabIds.length - 1;
        break;
      }
      default: {
        break;
      }
    }

    if (nextIndex !== null) {
      const nextTab = tabIds[nextIndex];
      if (!nextTab) return;
      event.preventDefault();
      setActiveTab(nextTab);
      const buttons = tabListReference.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
      buttons?.[nextIndex]?.focus();
    }
  };

  const Content = TAB_CONTENT[activeTab];

  return (
    <Dialog.Root
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) closeSettings();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay asChild>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className='fixed inset-0 z-50 bg-black/50 backdrop-blur-sm'
          />
        </Dialog.Overlay>
        <Dialog.Content
          asChild
          aria-describedby='settings-modal-description'
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            const activeButton = tabListReference.current?.querySelector<HTMLButtonElement>(
              '[role="tab"][aria-selected="true"]'
            );
            activeButton?.focus();
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', duration: 0.3 }}
            className='border-border bg-card fixed top-1/2 left-1/2 z-50 flex max-h-[min(600px,85vh)] w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border shadow-xl'
          >
            {/* Sidebar */}
            <div className='border-border bg-muted flex w-48 flex-col border-r'>
              <div className='border-border border-b px-4 py-4'>
                <Dialog.Title className='text-foreground text-lg font-semibold'>
                  Settings
                </Dialog.Title>
                <Dialog.Description id='settings-modal-description' className='sr-only'>
                  Manage your account settings and preferences.
                </Dialog.Description>
              </div>
              <div
                ref={tabListReference}
                role='tablist'
                aria-label='Settings sections'
                aria-orientation='vertical'
                className='flex-1 space-y-1 p-2'
                onKeyDown={handleTabKeyDown}
              >
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    role='tab'
                    id={`settings-tab-${tab.id}`}
                    aria-selected={activeTab === tab.id}
                    aria-controls={`settings-panel-${tab.id}`}
                    tabIndex={activeTab === tab.id ? 0 : -1}
                    onClick={() => {
                      setActiveTab(tab.id);
                    }}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors',
                      (() => {
                        if (activeTab === tab.id) {
                          return tab.danger
                            ? 'bg-destructive/10 text-destructive'
                            : 'bg-accent text-foreground';
                        }
                        return tab.danger
                          ? 'text-destructive hover:bg-destructive/5'
                          : 'text-muted-foreground hover:bg-accent';
                      })()
                    )}
                  >
                    {tab.icon}
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Content Area */}
            <div className='flex flex-1 flex-col overflow-hidden'>
              {/* Close Button */}
              <Dialog.Close asChild>
                <Button
                  variant='ghost'
                  size='icon'
                  className='text-muted-foreground hover:text-foreground absolute top-3 right-3 z-10 h-8 w-8'
                  aria-label='Close settings'
                >
                  <X className='h-4 w-4' aria-hidden='true' />
                </Button>
              </Dialog.Close>

              {/* Tab Content with transition */}
              <div
                role='tabpanel'
                id={`settings-panel-${activeTab}`}
                aria-labelledby={`settings-tab-${activeTab}`}
                className='flex-1 overflow-y-auto p-6'
              >
                <AnimatePresence mode='wait'>
                  <motion.div
                    key={activeTab}
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -8 }}
                    transition={{ duration: 0.15 }}
                  >
                    <Content />
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>
          </motion.div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
