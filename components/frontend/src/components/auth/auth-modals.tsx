import { useModalStore } from '@/stores/modal-store';

import { LoginModal } from './login-modal';
import { PasswordResetModal } from './password-reset-modal';
import { RegisterModal } from './register-modal';
import { VerifyOtpModal } from './verify-otp-modal';

/**
 * AuthModals - Container component that renders authentication modals
 * based on the modal store state.
 *
 * This component should be placed once in the app (typically in MainLayout)
 * and the modals can be opened from anywhere using the useModalStore hook.
 */
export function AuthModals() {
  const { activeModal, pendingEmail, closeModal, switchToLogin, switchToRegister } =
    useModalStore();

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
      <VerifyOtpModal
        isOpen={activeModal === 'verify-otp'}
        email={pendingEmail ?? ''}
        onClose={closeModal}
        onSwitchToLogin={switchToLogin}
      />
      <PasswordResetModal
        isOpen={activeModal === 'password-reset'}
        initialEmail={pendingEmail}
        onClose={closeModal}
        onSwitchToLogin={switchToLogin}
      />
    </>
  );
}
