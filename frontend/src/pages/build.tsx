import { BuildView } from '@/components/build-view';
import { useAuth } from '@/context/auth-context';
import { useModal } from '@/context/modal-context';

/**
 * Build page - Developer portal and documentation.
 */
export default function BuildPage() {
  const { user } = useAuth();
  const { openLogin } = useModal();

  return <BuildView onAuthRequired={user ? undefined : openLogin} />;
}
