import { useState, useEffect, useCallback } from 'react';
import { EventsOn, EventsOff } from '../../wailsjs/runtime/runtime';
import { GetStatus, GetEndpoints, GetConfig, Start, Stop, ReloadEndpoints } from '../../wailsjs/go/main/App';
import { main } from '../../wailsjs/go/models';

type StatusInfo = main.StatusInfo;
type EndpointInfo = main.EndpointInfo;
type ConfigInfo = main.ConfigInfo;
type AppState = 'idle' | 'starting' | 'running' | 'stopping' | 'error';

/**
 * Custom hook for managing app state and communicating with Go backend.
 * Follows react-expert pattern: local state for component-specific data.
 */
export function useApp() {
  const [status, setStatus] = useState<StatusInfo>(new main.StatusInfo({
    state: 'idle',
    mode: 'HTTP',
  }));
  const [endpoints, setEndpoints] = useState<EndpointInfo[]>([]);
  const [config, setConfig] = useState<ConfigInfo | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch initial data on mount
  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        const [statusData, endpointsData, configData] = await Promise.all([
          GetStatus(),
          GetEndpoints(),
          GetConfig(),
        ]);
        setStatus(statusData);
        setEndpoints(endpointsData);
        setConfig(configData);
      } catch (err) {
        console.error('Failed to fetch initial data:', err);
        setError('Failed to connect to backend');
      }
    };
    fetchInitialData();
  }, []);

  // Subscribe to Go events
  useEffect(() => {
    // Listen for state changes from Go backend
    EventsOn('app:state-changed', (data: StatusInfo) => {
      setStatus(data);
      if (data.state === 'error' && data.errorMessage) {
        setError(data.errorMessage);
      } else if (data.state !== 'error') {
        setError(null);
      }
    });

    // Listen for endpoint changes
    EventsOn('app:endpoints-changed', (data: EndpointInfo[]) => {
      setEndpoints(data);
    });

    // Cleanup subscriptions on unmount
    return () => {
      EventsOff('app:state-changed');
      EventsOff('app:endpoints-changed');
    };
  }, []);

  const start = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await Start();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const stop = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await Stop();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reload = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await ReloadEndpoints();
      // Refresh endpoints list
      const endpointsData = await GetEndpoints();
      setEndpoints(endpointsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reload endpoints');
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    status,
    endpoints,
    config,
    isLoading,
    error,
    actions: {
      start,
      stop,
      reload,
    },
  };
}

export type { StatusInfo, EndpointInfo, ConfigInfo, AppState };
