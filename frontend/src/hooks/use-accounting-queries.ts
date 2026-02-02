import type { CreateTransactionInput } from '@/lib/types';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAccountingContext } from '@/context/accounting-context';
import {
  AccountingProxyClient,
  parseTransaction,
  POLLING_INTERVAL_MS
} from '@/hooks/use-accounting-api';
import { accountingKeys } from '@/lib/query-keys';

// Singleton proxy client
let proxyClientInstance: AccountingProxyClient | null = null;

function getProxyClient(): AccountingProxyClient {
  proxyClientInstance ??= new AccountingProxyClient();
  return proxyClientInstance;
}

export function useAccountingUserQuery() {
  const { isConfigured } = useAccountingContext();

  return useQuery({
    queryKey: accountingKeys.user(),
    queryFn: () => getProxyClient().getUser(),
    enabled: isConfigured,
    refetchInterval: POLLING_INTERVAL_MS,
    refetchIntervalInBackground: false
  });
}

export function useAccountingBalanceQuery() {
  const result = useAccountingUserQuery();
  return {
    ...result,
    data: result.data?.balance ?? null
  };
}

export function useTransactionsQuery(pageSize = 20) {
  const { isConfigured } = useAccountingContext();

  return useQuery({
    queryKey: accountingKeys.transactions(pageSize),
    queryFn: async () => {
      const response = await getProxyClient().getTransactions(0, pageSize);
      return response.map((tx) => parseTransaction(tx));
    },
    enabled: isConfigured,
    refetchInterval: POLLING_INTERVAL_MS,
    refetchIntervalInBackground: false
  });
}

export function useCreateTransactionMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (input: CreateTransactionInput) => {
      const response = await getProxyClient().createTransaction(input);
      return parseTransaction(response);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accountingKeys.all });
    }
  });
}

export function useConfirmTransactionMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (transactionId: string) => {
      const response = await getProxyClient().confirmTransaction(transactionId);
      return parseTransaction(response);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accountingKeys.all });
    }
  });
}

export function useCancelTransactionMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (transactionId: string) => {
      const response = await getProxyClient().cancelTransaction(transactionId);
      return parseTransaction(response);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: accountingKeys.all });
    }
  });
}
