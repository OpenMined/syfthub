import { BuildView } from '@/components/build/build-view';
import { useAuth } from '@/context/auth-context';
import { useModalStore } from '@/stores/modal-store';

/**
 * Build page - Developer portal and documentation.
 */
export default function BuildPage() {
  const { user } = useAuth();
  const { openLogin } = useModalStore();

  return <BuildView onAuthRequired={user ? undefined : openLogin} />;
}
