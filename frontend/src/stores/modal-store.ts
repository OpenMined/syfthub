import { create } from 'zustand';

type ModalType = 'login' | 'register' | null;

interface ModalState {
  activeModal: ModalType;
  openLogin: () => void;
  openRegister: () => void;
  closeModal: () => void;
  switchToLogin: () => void;
  switchToRegister: () => void;
}

export const useModalStore = create<ModalState>((set) => ({
  activeModal: null,
  openLogin: () => {
    set({ activeModal: 'login' });
  },
  openRegister: () => {
    set({ activeModal: 'register' });
  },
  closeModal: () => {
    set({ activeModal: null });
  },
  switchToLogin: () => {
    set({ activeModal: 'login' });
  },
  switchToRegister: () => {
    set({ activeModal: 'register' });
  }
}));
