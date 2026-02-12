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

const STORAGE_KEY = 'syfthub-theme';

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

/**
 * Get the system's preferred color scheme
 */
function getSystemTheme(): ResolvedTheme {
  // SSR check: window is not available during server-side rendering
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, sonarjs/different-types-comparison -- SSR guard
  if (globalThis.window === undefined) return 'light';
  return globalThis.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/**
 * Get the stored theme from localStorage
 */
function getStoredTheme(defaultTheme: Theme = 'system'): Theme {
  // SSR check: window/localStorage is not available during server-side rendering
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition, sonarjs/different-types-comparison -- SSR guard
  if (globalThis.window === undefined) return defaultTheme;
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored;
  }
  return defaultTheme;
}

/**
 * Apply the theme class to the document
 */
function applyThemeToDocument(resolvedTheme: ResolvedTheme): void {
  const root = document.documentElement;
  root.classList.toggle('dark', resolvedTheme === 'dark');
}

interface ThemeProviderProps {
  children: React.ReactNode;
  /** Default theme if none is stored. Defaults to 'system' */
  defaultTheme?: Theme;
}

/**
 * ThemeProvider - Manages light/dark mode state and persistence.
 *
 * Features:
 * - Persists theme preference to localStorage
 * - Supports system preference with automatic updates
 * - Applies .dark class to document root for Tailwind
 * - Prevents flash of wrong theme (when used with inline script in index.html)
 */
export function ThemeProvider({ children, defaultTheme = 'system' }: Readonly<ThemeProviderProps>) {
  // Initialize from localStorage (uses defaultTheme if nothing stored)
  const [theme, setThemeState] = useState<Theme>(() => getStoredTheme(defaultTheme));

  // Track the resolved theme (what's actually applied)
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => {
    const currentTheme = getStoredTheme(defaultTheme);
    return currentTheme === 'system' ? getSystemTheme() : currentTheme;
  });

  // Update theme and persist to localStorage
  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem(STORAGE_KEY, newTheme);
  }, []);

  // Apply theme to document and track resolved theme
  useEffect(() => {
    const resolved = theme === 'system' ? getSystemTheme() : theme;
    setResolvedTheme(resolved);
    applyThemeToDocument(resolved);
  }, [theme]);

  // Listen for system preference changes when in "system" mode
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
    () => ({
      theme,
      setTheme,
      resolvedTheme
    }),
    [theme, setTheme, resolvedTheme]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/**
 * useTheme - Access theme state and controls.
 *
 * @returns {ThemeContextValue} Theme state and setter
 * @throws {Error} If used outside ThemeProvider
 *
 * @example
 * const { theme, setTheme, resolvedTheme } = useTheme();
 *
 * // Toggle between light and dark
 * setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
 *
 * // Use system preference
 * setTheme('system');
 */
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
