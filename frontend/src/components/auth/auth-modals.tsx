import { useModal } from '@/context/modal-context';

import { LoginModal } from './login-modal';
import { RegisterModal } from './register-modal';

/**
 * AuthModals - Container component that renders authentication modals
 * based on the ModalContext state.
 *
 * This component should be placed once in the app (typically in MainLayout)
 * and the modals can be opened from anywhere using the useModal hook.
 */
export function AuthModals() {
  const { activeModal, closeModal, switchToLogin, switchToRegister } = useModal();

  return (
    <>
      <LoginModal
        isOpen={activeModal === 'login'}
        onClose={closeModal}
        onSwitchToRegister={switchToRegister}
      />
      <RegisterModal
        isOpen={activeModal === 'register'}
        onClose={closeModal}
        onSwitchToLogin={switchToLogin}
      />
    </>
  );
}
