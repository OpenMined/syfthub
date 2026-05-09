/**
 * useTempoWallet — Consumer hook for the browser-local Tempo payment wallet.
 *
 * Distinct from `useWallet()` (which exposes the SyftHub backend Xendit
 * credit wallet). This hook is used by the chat UI to sign MPP payment
 * challenges with an on-chain Tempo ERC-20 transfer.
 */

import { useContext } from 'react';

import type { TempoWalletContextValue } from '@/context/tempo-wallet-context';

import { TempoWalletContext } from '@/context/tempo-wallet-context';

export function useTempoWallet(): TempoWalletContextValue {
  const ctx = useContext(TempoWalletContext);
  if (!ctx) {
    throw new Error('useTempoWallet must be used inside <TempoWalletProvider>');
  }
  return ctx;
}
