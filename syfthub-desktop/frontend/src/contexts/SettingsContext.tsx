import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { HasSettings, GetSettings, SaveSettingsData, GetDefaultEndpointsPath } from '../../wailsjs/go/main/App';
import { main } from '../../wailsjs/go/models';

type Settings = main.Settings;

interface SettingsContextValue {
  settings: Settings | null;
  isConfigured: boolean;
  isLoading: boolean;
  error: string | null;
  defaultEndpointsPath: string;
  saveSettings: (syfthubUrl: string, apiKey: string, endpointsPath: string) => Promise<void>;
  refreshSettings: () => Promise<void>;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

interface SettingsProviderProps {
  children: ReactNode;
}

export function SettingsProvider({ children }: SettingsProviderProps) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [isConfigured, setIsConfigured] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [defaultEndpointsPath, setDefaultEndpointsPath] = useState<string>('');

  // Load settings on mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        setIsLoading(true);
        const [hasSettingsResult, settingsData, defaultPath] = await Promise.all([
          HasSettings(),
          GetSettings(),
          GetDefaultEndpointsPath(),
        ]);
        setIsConfigured(hasSettingsResult);
        setSettings(settingsData);
        setDefaultEndpointsPath(defaultPath);
        setError(null);
      } catch (err) {
        console.error('Failed to load settings:', err);
        setError('Failed to load settings');
      } finally {
        setIsLoading(false);
      }
    };
    loadSettings();
  }, []);

  const saveSettings = useCallback(async (syfthubUrl: string, apiKey: string, endpointsPath: string) => {
    try {
      setError(null);
      await SaveSettingsData(syfthubUrl, apiKey, endpointsPath);
      // Refresh settings after save
      const settingsData = await GetSettings();
      setSettings(settingsData);
      setIsConfigured(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save settings';
      setError(message);
      throw err;
    }
  }, []);

  const refreshSettings = useCallback(async () => {
    try {
      setIsLoading(true);
      const [hasSettingsResult, settingsData] = await Promise.all([
        HasSettings(),
        GetSettings(),
      ]);
      setIsConfigured(hasSettingsResult);
      setSettings(settingsData);
      setError(null);
    } catch (err) {
      console.error('Failed to refresh settings:', err);
      setError('Failed to refresh settings');
    } finally {
      setIsLoading(false);
    }
  }, []);

  return (
    <SettingsContext.Provider
      value={{
        settings,
        isConfigured,
        isLoading,
        error,
        defaultEndpointsPath,
        saveSettings,
        refreshSettings,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
}
