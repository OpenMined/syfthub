import type {
  UserAggregator,
  UserAggregatorCreate,
  UserAggregatorListResponse,
  UserAggregatorUpdate
} from '@/lib/types';

import { create } from 'zustand';

interface UserAggregatorsState {
  // Data
  aggregators: UserAggregator[];
  defaultAggregatorId: number | null;

  // Loading states
  isLoading: boolean;
  isCreating: boolean;
  isUpdating: boolean;
  isDeleting: boolean;

  // Error states
  error: string | null;

  // Actions
  fetchAggregators: () => Promise<void>;
  createAggregator: (data: UserAggregatorCreate) => Promise<UserAggregator | null>;
  updateAggregator: (id: number, data: UserAggregatorUpdate) => Promise<UserAggregator | null>;
  deleteAggregator: (id: number) => Promise<boolean>;
  setDefaultAggregator: (id: number) => Promise<UserAggregator | null>;
  clearError: () => void;
}

const API_BASE = '/api/v1/users/me/aggregators';

async function getAuthHeaders(): Promise<Record<string, string>> {
  // Import dynamically to avoid circular dependencies
  const { syftClient } = await import('@/lib/sdk-client');
  const tokens = syftClient.getTokens();
  const accessToken = tokens?.accessToken ?? '';
  return {
    Authorization: `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  };
}

export const useUserAggregatorsStore = create<UserAggregatorsState>((set, get) => ({
  // Initial state
  aggregators: [],
  defaultAggregatorId: null,
  isLoading: false,
  isCreating: false,
  isUpdating: false,
  isDeleting: false,
  error: null,

  // Fetch all aggregators
  fetchAggregators: async () => {
    set({ isLoading: true, error: null });
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(API_BASE, { headers });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errorData.detail ?? 'Failed to fetch aggregators');
      }

      const data = (await response.json()) as UserAggregatorListResponse;
      set({
        aggregators: data.aggregators,
        defaultAggregatorId: data.default_aggregator_id,
        isLoading: false
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'An unknown error occurred',
        isLoading: false
      });
    }
  },

  // Create new aggregator
  createAggregator: async (data: UserAggregatorCreate) => {
    set({ isCreating: true, error: null });
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(API_BASE, {
        method: 'POST',
        headers,
        body: JSON.stringify(data)
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errorData.detail ?? 'Failed to create aggregator');
      }

      const newAggregator = (await response.json()) as UserAggregator;

      // Update local state
      const currentAggregators = get().aggregators;
      set({
        aggregators: [newAggregator, ...currentAggregators],
        isCreating: false
      });

      // If this was set as default, update default ID
      if (newAggregator.is_default) {
        set({ defaultAggregatorId: newAggregator.id });
      }

      return newAggregator;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'An unknown error occurred',
        isCreating: false
      });
      return null;
    }
  },

  // Update aggregator
  updateAggregator: async (id: number, data: UserAggregatorUpdate) => {
    set({ isUpdating: true, error: null });
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE}/${id}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(data)
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errorData.detail ?? 'Failed to update aggregator');
      }

      const updatedAggregator = (await response.json()) as UserAggregator;

      // Update local state
      const currentAggregators = get().aggregators;
      const updatedAggregators = currentAggregators.map((agg) =>
        agg.id === id ? updatedAggregator : agg
      );

      set({
        aggregators: updatedAggregators,
        isUpdating: false
      });

      // Update default ID if needed
      if (data.is_default === true) {
        set({ defaultAggregatorId: id });
      }

      return updatedAggregator;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'An unknown error occurred',
        isUpdating: false
      });
      return null;
    }
  },

  // Delete aggregator
  deleteAggregator: async (id: number) => {
    set({ isDeleting: true, error: null });
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE}/${id}`, {
        method: 'DELETE',
        headers
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errorData.detail ?? 'Failed to delete aggregator');
      }

      // Update local state
      const currentAggregators = get().aggregators;
      const remainingAggregators = currentAggregators.filter((agg) => agg.id !== id);

      // If we deleted the default, find the new default from remaining
      let newDefaultId = get().defaultAggregatorId;
      const wasDefault = currentAggregators.find((agg) => agg.id === id)?.is_default ?? false;
      if (wasDefault && remainingAggregators.length > 0) {
        newDefaultId = remainingAggregators[0]?.id ?? null;
        // Update the is_default flag on the new default in our local state
        if (remainingAggregators[0]) {
          remainingAggregators[0].is_default = true;
        }
      } else if (remainingAggregators.length === 0) {
        newDefaultId = null;
      }

      set({
        aggregators: remainingAggregators,
        defaultAggregatorId: newDefaultId,
        isDeleting: false
      });

      return true;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'An unknown error occurred',
        isDeleting: false
      });
      return false;
    }
  },

  // Set default aggregator
  setDefaultAggregator: async (id: number) => {
    set({ isUpdating: true, error: null });
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE}/${id}/default`, {
        method: 'PATCH',
        headers
      });

      if (!response.ok) {
        const errorData = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(errorData.detail ?? 'Failed to set default aggregator');
      }

      const updatedAggregator = (await response.json()) as UserAggregator;

      // Update local state - update is_default for all aggregators
      const currentAggregators = get().aggregators;
      const updatedAggregators = currentAggregators.map((agg) => ({
        ...agg,
        is_default: agg.id === id
      }));

      set({
        aggregators: updatedAggregators,
        defaultAggregatorId: id,
        isUpdating: false
      });

      return updatedAggregator;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'An unknown error occurred',
        isUpdating: false
      });
      return null;
    }
  },

  // Clear error
  clearError: () => {
    set({ error: null });
  }
}));
