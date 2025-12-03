import React, { createContext, useCallback, useContext, useState } from 'react';

type ModalType = 'login' | 'register' | null;

interface ModalContextType {
  activeModal: ModalType;
  openLogin: () => void;
  openRegister: () => void;
  closeModal: () => void;
  switchToLogin: () => void;
  switchToRegister: () => void;
}

const ModalContext = createContext<ModalContextType | undefined>(undefined);

interface ModalProviderProperties {
  children: React.ReactNode;
}

export function ModalProvider({ children }: Readonly<ModalProviderProperties>) {
  const [activeModal, setActiveModal] = useState<ModalType>(null);

  const openLogin = useCallback(() => {
    setActiveModal('login');
  }, []);

  const openRegister = useCallback(() => {
    setActiveModal('register');
  }, []);

  const closeModal = useCallback(() => {
    setActiveModal(null);
  }, []);

  const switchToLogin = useCallback(() => {
    setActiveModal('login');
  }, []);

  const switchToRegister = useCallback(() => {
    setActiveModal('register');
  }, []);

  const value: ModalContextType = {
    activeModal,
    openLogin,
    openRegister,
    closeModal,
    switchToLogin,
    switchToRegister
  };

  return <ModalContext.Provider value={value}>{children}</ModalContext.Provider>;
}

// Custom hook to use modal context
export function useModal(): ModalContextType {
  const context = useContext(ModalContext);
  if (context === undefined) {
    throw new Error('useModal must be used within a ModalProvider');
  }
  return context;
}
