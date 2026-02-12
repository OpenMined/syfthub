import { create } from 'zustand';

export type SettingsTab = 'profile' | 'security' | 'payment' | 'aggregator' | 'danger-zone';

interface SettingsModalState {
  isOpen: boolean;
  activeTab: SettingsTab;
  openSettings: (tab?: SettingsTab) => void;
  closeSettings: () => void;
  setActiveTab: (tab: SettingsTab) => void;
}

export const useSettingsModalStore = create<SettingsModalState>((set) => ({
  isOpen: false,
  activeTab: 'profile',
  openSettings: (tab?: SettingsTab) => {
    set((state) => ({
      isOpen: true,
      activeTab: tab ?? state.activeTab
    }));
  },
  closeSettings: () => {
    set({ isOpen: false, activeTab: 'profile' });
  },
  setActiveTab: (tab: SettingsTab) => {
    set({ activeTab: tab });
  }
}));
