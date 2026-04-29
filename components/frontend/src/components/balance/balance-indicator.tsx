import { useCallback, useEffect, useRef, useState } from 'react';

import { AnimatePresence, motion } from 'framer-motion';
import AlertCircle from 'lucide-react/dist/esm/icons/alert-circle';
import ChevronDown from 'lucide-react/dist/esm/icons/chevron-down';
import Coins from 'lucide-react/dist/esm/icons/coins';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';

import { OnboardingCallout } from '@/components/onboarding';
import { useWalletContext } from '@/context/wallet-context';
import { useWalletBalance } from '@/hooks/use-wallet-api';
import { cn } from '@/lib/utils';
import { useSettingsModalStore } from '@/stores/settings-modal-store';

import {
  formatBalanceCompact,
  getBalanceStatus,
  statusColors,
  statusRingColors
} from './balance-display';
import { CreditsPanel } from './credits-panel';

/**
 * BalanceIndicator — top-bar pill that opens the unified Credits Panel.
 *
 * The pill itself stays focused on the MPP wallet balance (the universal
 * SyftHub wallet); endpoint subscriptions live inside the dropdown so the
 * nav stays visually quiet.
 */
export function BalanceIndicator() {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownReference = useRef<HTMLDivElement>(null);
  const buttonReference = useRef<HTMLButtonElement>(null);

  const { isConfigured, isLoading: isLoadingWallet } = useWalletContext();
  const { balance: walletBalance, isLoading: isLoadingBalance, error } = useWalletBalance();
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

  if (!isConfigured) {
    return (
      <OnboardingCallout step='balance' position='bottom'>
        <div className='relative'>
          <button
            ref={buttonReference}
            onClick={toggleOpen}
            className={cn(
              'font-inter flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition-colors',
              'border-amber-200 bg-amber-50 text-amber-700',
              'hover:border-amber-300 hover:bg-amber-100'
            )}
            aria-expanded={isOpen}
            aria-haspopup='true'
          >
            <Coins className='h-3.5 w-3.5' aria-hidden='true' />
            <span>Set up wallet</span>
            <ChevronDown className={cn('h-3 w-3 transition-transform', isOpen && 'rotate-180')} />
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

  const isLoading = isLoadingBalance;
  const balance = walletBalance?.balance ?? 0;
  const status = getBalanceStatus(balance);

  const renderStatusIcon = () => {
    if (isLoading) {
      return <Loader2 className='text-muted-foreground h-3.5 w-3.5 animate-spin' />;
    }
    if (error) {
      return <AlertCircle className='h-3.5 w-3.5 text-red-500' />;
    }
    return (
      <div className='relative'>
        <div
          className={cn(
            'h-2 w-2 rounded-full',
            statusColors[status],
            status === 'empty' && 'animate-pulse'
          )}
        />
        <div
          className={cn('absolute inset-0 h-2 w-2 rounded-full ring-2', statusRingColors[status])}
        />
      </div>
    );
  };

  return (
    <OnboardingCallout step='balance' position='bottom'>
      <div className='relative'>
        <button
          ref={buttonReference}
          onClick={toggleOpen}
          className={cn(
            'font-inter flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors transition-shadow',
            'border-border bg-muted',
            'hover:border-input hover:shadow-sm',
            'focus:ring-ring/20 focus:ring-2 focus:outline-none'
          )}
          aria-label={`Account balance: ${formatBalanceCompact(balance)}`}
          aria-expanded={isOpen}
          aria-haspopup='true'
        >
          {renderStatusIcon()}
          <span className='text-foreground font-medium tabular-nums'>
            {error ? 'Error' : formatBalanceCompact(balance)}
          </span>
          <ChevronDown
            className={cn(
              'text-muted-foreground h-3 w-3 transition-transform',
              isOpen && 'rotate-180'
            )}
          />
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
