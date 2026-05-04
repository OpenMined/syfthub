import { useCallback, useEffect, useRef, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import Wallet from 'lucide-react/dist/esm/icons/wallet';

import { OnboardingCallout } from '@/components/onboarding';
import { useWalletContext } from '@/context/wallet-context';
import { cn } from '@/lib/utils';
import { useSettingsModalStore } from '@/stores/settings-modal-store';

import { CreditsPanel } from './credits-panel';

/**
 * BalanceIndicator — top-bar wallet icon that opens the unified Credits Panel.
 *
 * The trigger is intentionally minimal (icon only). Showing a single number
 * here was confusing for users who had just paid but whose balance was still
 * settling — the per-wallet detail belongs inside the dropdown panel.
 */
export function BalanceIndicator() {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownReference = useRef<HTMLDivElement>(null);
  const buttonReference = useRef<HTMLButtonElement>(null);

  const { isConfigured, isLoading: isLoadingWallet } = useWalletContext();
  const { openSettings } = useSettingsModalStore();

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownReference.current &&
        buttonReference.current &&
        !dropdownReference.current.contains(event.target as Node) &&
        !buttonReference.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [isOpen]);

  useEffect(() => {
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setIsOpen(false);
    }
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => {
        document.removeEventListener('keydown', handleEscape);
      };
    }
  }, [isOpen]);

  const closePanel = useCallback(() => {
    setIsOpen(false);
  }, []);

  const handleOpenWalletSettings = useCallback(() => {
    setIsOpen(false);
    openSettings('payment');
  }, [openSettings]);

  const handleOpenSubscriptionsSettings = useCallback(() => {
    setIsOpen(false);
    openSettings('subscriptions');
  }, [openSettings]);

  const toggleOpen = useCallback(() => {
    setIsOpen((previous) => !previous);
  }, []);

  if (isLoadingWallet) return null;

  return (
    <OnboardingCallout step='balance' position='bottom'>
      <div className='relative'>
        <button
          ref={buttonReference}
          type='button'
          onClick={toggleOpen}
          className={cn(
            'relative inline-flex h-9 w-9 items-center justify-center rounded-lg border transition-colors transition-shadow',
            'border-border bg-muted text-muted-foreground',
            'hover:border-input hover:text-foreground hover:shadow-sm',
            'focus:ring-ring/20 focus:ring-2 focus:outline-none'
          )}
          aria-label='Wallet'
          aria-expanded={isOpen}
          aria-haspopup='true'
        >
          <Wallet className='h-4 w-4' aria-hidden='true' />
          {!isConfigured && (
            <span
              aria-hidden='true'
              className='ring-background absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-amber-500 ring-2'
            />
          )}
        </button>

        <Dropdown
          isOpen={isOpen}
          dropdownReference={dropdownReference}
          onClose={closePanel}
          onOpenWalletSettings={handleOpenWalletSettings}
          onOpenSubscriptionsSettings={handleOpenSubscriptionsSettings}
        />
      </div>
    </OnboardingCallout>
  );
}

interface DropdownProperties {
  isOpen: boolean;
  dropdownReference: React.RefObject<HTMLDivElement | null>;
  onClose: () => void;
  onOpenWalletSettings: () => void;
  onOpenSubscriptionsSettings: () => void;
}

function Dropdown({
  isOpen,
  dropdownReference,
  onClose,
  onOpenWalletSettings,
  onOpenSubscriptionsSettings
}: Readonly<DropdownProperties>) {
  return (
    <AnimatePresence>
      {isOpen ? (
        <motion.div
          ref={dropdownReference}
          initial={{ opacity: 0, y: -8, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -8, scale: 0.96 }}
          transition={{ duration: 0.15, ease: 'easeOut' }}
          className={cn(
            'absolute top-full right-0 z-50 mt-2 w-[360px]',
            'bg-card border-border rounded-xl border shadow-lg'
          )}
        >
          <CreditsPanel
            enabled={isOpen}
            onClose={onClose}
            onOpenWalletSettings={onOpenWalletSettings}
            onOpenSubscriptionsSettings={onOpenSubscriptionsSettings}
          />
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
