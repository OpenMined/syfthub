import React, { createContext, useCallback, useContext, useState } from 'react';

export type SettingsTab = 'profile' | 'security' | 'payment' | 'aggregator' | 'danger-zone';

interface SettingsModalContextType {
  isOpen: boolean;
  activeTab: SettingsTab;
  openSettings: (tab?: SettingsTab) => void;
  closeSettings: () => void;
  setActiveTab: (tab: SettingsTab) => void;
}

const SettingsModalContext = createContext<SettingsModalContextType | undefined>(undefined);

interface SettingsModalProviderProperties {
  children: React.ReactNode;
}

export function SettingsModalProvider({ children }: Readonly<SettingsModalProviderProperties>) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTabState] = useState<SettingsTab>('profile');

  const openSettings = useCallback((tab?: SettingsTab) => {
    if (tab) {
      setActiveTabState(tab);
    }
    setIsOpen(true);
  }, []);

  const closeSettings = useCallback(() => {
    setIsOpen(false);
    // Reset to profile tab when closing
    setActiveTabState('profile');
  }, []);

  const setActiveTab = useCallback((tab: SettingsTab) => {
    setActiveTabState(tab);
  }, []);

  const value: SettingsModalContextType = {
    isOpen,
    activeTab,
    openSettings,
    closeSettings,
    setActiveTab
  };

  return <SettingsModalContext.Provider value={value}>{children}</SettingsModalContext.Provider>;
}

// Custom hook to use settings modal context
export function useSettingsModal(): SettingsModalContextType {
  const context = useContext(SettingsModalContext);
  if (context === undefined) {
    throw new Error('useSettingsModal must be used within a SettingsModalProvider');
  }
  return context;
}
