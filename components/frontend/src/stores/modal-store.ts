import { create } from 'zustand';

type ModalType = 'login' | 'register' | 'verify-otp' | 'password-reset' | null;

interface ModalState {
  activeModal: ModalType;
  /** Email address carried between modals (e.g. register → verify-otp). */
  pendingEmail: string | null;
  openLogin: () => void;
  openRegister: () => void;
  openVerifyOtp: (email: string) => void;
  openPasswordReset: (email?: string) => void;
  closeModal: () => void;
  switchToLogin: () => void;
  switchToRegister: () => void;
}

export const useModalStore = create<ModalState>((set) => ({
  activeModal: null,
  pendingEmail: null,
  openLogin: () => {
    set({ activeModal: 'login', pendingEmail: null });
  },
  openRegister: () => {
    set({ activeModal: 'register', pendingEmail: null });
  },
  openVerifyOtp: (email: string) => {
    set({ activeModal: 'verify-otp', pendingEmail: email });
  },
  openPasswordReset: (email?: string) => {
    set({ activeModal: 'password-reset', pendingEmail: email ?? null });
  },
  closeModal: () => {
    set({ activeModal: null, pendingEmail: null });
  },
  switchToLogin: () => {
    set({ activeModal: 'login', pendingEmail: null });
  },
  switchToRegister: () => {
    set({ activeModal: 'register', pendingEmail: null });
  }
}));
