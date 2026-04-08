import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

type Theme = 'light' | 'dark' | 'system';
type ResolvedTheme = 'light' | 'dark';

interface ThemeContextValue {
  /** User's theme preference: light, dark, or system */
  theme: Theme;
  /** Set the theme preference */
  setTheme: (theme: Theme) => void;
  /** The actual applied theme (resolves "system" to light/dark) */
  resolvedTheme: ResolvedTheme;
}

const STORAGE_KEY = 'syfthub-desktop-theme';

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function getSystemTheme(): ResolvedTheme {
  if (globalThis.window === undefined) return 'light';
  return globalThis.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getStoredTheme(defaultTheme: Theme = 'system'): Theme {
  if (globalThis.window === undefined) return defaultTheme;
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored;
  }
  return defaultTheme;
}

function applyThemeToDocument(resolvedTheme: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.toggle('dark', resolvedTheme === 'dark');
}

interface ThemeProviderProps {
  children: React.ReactNode;
  defaultTheme?: Theme;
}

export function ThemeProvider({ children, defaultTheme = 'system' }: Readonly<ThemeProviderProps>) {
  const [theme, setThemeState] = useState<Theme>(() => getStoredTheme(defaultTheme));

  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => {
    const currentTheme = getStoredTheme(defaultTheme);
    return currentTheme === 'system' ? getSystemTheme() : currentTheme;
  });

  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem(STORAGE_KEY, newTheme);
  }, []);

  useEffect(() => {
    const resolved = theme === 'system' ? getSystemTheme() : theme;
    setResolvedTheme(resolved);
    applyThemeToDocument(resolved);
  }, [theme]);

  useEffect(() => {
    if (theme !== 'system') return;

    const mediaQuery = globalThis.matchMedia('(prefers-color-scheme: dark)');

    const handleChange = (event: MediaQueryListEvent) => {
      const newResolved = event.matches ? 'dark' : 'light';
      setResolvedTheme(newResolved);
      applyThemeToDocument(newResolved);
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => {
      mediaQuery.removeEventListener('change', handleChange);
    };
  }, [theme]);

  const value = useMemo(
    () => ({ theme, setTheme, resolvedTheme }),
    [theme, setTheme, resolvedTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
