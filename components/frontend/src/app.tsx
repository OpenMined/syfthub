import { GoogleOAuthProvider } from '@react-oauth/google';
import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { ProtectedRoute } from './components/auth/protected-route';
import RootProvider from './components/providers/root';
import { RouteBoundary } from './components/route-boundary';
import { ScrollToTop } from './components/scroll-to-top';
import { AccountingProvider } from './context/accounting-context';
import { AuthProvider } from './context/auth-context';
import { MainLayout } from './layouts/main-layout';
import { lazyWithRetry } from './lib/lazy-with-retry';
import { queryClient } from './lib/query-client';
import { getGoogleClientId } from './lib/sdk-client';
import { ErrorBoundary } from './observability';

// Get Google OAuth Client ID from environment
const googleClientId = getGoogleClientId();

// Lazy load all pages for code splitting (with auto-reload on stale chunks)
const HomePage = lazyWithRetry(() => import('./pages/home'));
const BrowsePage = lazyWithRetry(() => import('./pages/browse'));
const ChatPage = lazyWithRetry(() => import('./pages/chat'));
const BuildPage = lazyWithRetry(() => import('./pages/build'));
const AboutPage = lazyWithRetry(() => import('./pages/about'));
const ProfilePage = lazyWithRetry(() => import('./pages/profile'));
const EndpointsPage = lazyWithRetry(() => import('./pages/endpoints'));
const EndpointDetailPage = lazyWithRetry(() => import('./pages/endpoint-detail'));
const AgentPage = lazyWithRetry(() => import('./pages/agent'));
const NotFoundPage = lazyWithRetry(() => import('./pages/not-found'));
const QueryPage = lazyWithRetry(() => import('./pages/query'));

/**
 * App - Root application component with routing configuration.
 *
 * Route structure:
 * - / : Home page with hero and recent items
 * - /browse : Browse data sources
 * - /chat : AI chat interface
 * - /build : Developer portal
 * - /profile : User profile (protected)
 * - /endpoints : Endpoint management with onboarding (protected)
 * - /:username/:slug : GitHub-style endpoint detail
 * - * : 404 Not Found
 *
 * All routes are wrapped in MainLayout which provides:
 * - Sidebar navigation
 * - User menu
 * - Auth modals
 *
 * Each lazy-loaded route has its own RouteBoundary (Suspense + ErrorBoundary)
 */
/**
 * Wrapper component that conditionally provides GoogleOAuthProvider
 * only when Google OAuth is configured.
 */
function GoogleOAuthWrapper({ children }: Readonly<{ children: React.ReactNode }>) {
  if (googleClientId) {
    return <GoogleOAuthProvider clientId={googleClientId}>{children}</GoogleOAuthProvider>;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RootProvider>
          <GoogleOAuthWrapper>
            <AuthProvider>
              <AccountingProvider>
                <BrowserRouter>
                  <ScrollToTop />
                  <Routes>
                    {/* URL query page — no layout chrome, prompt stays client-side */}
                    <Route
                      path='q'
                      element={
                        <RouteBoundary>
                          <QueryPage />
                        </RouteBoundary>
                      }
                    />
                    <Route element={<MainLayout />}>
                      {/* Public routes */}
                      <Route
                        index
                        element={
                          <RouteBoundary>
                            <HomePage />
                          </RouteBoundary>
                        }
                      />
                      <Route
                        path='browse'
                        element={
                          <RouteBoundary>
                            <BrowsePage />
                          </RouteBoundary>
                        }
                      />
                      <Route
                        path='chat'
                        element={
                          <RouteBoundary>
                            <ChatPage />
                          </RouteBoundary>
                        }
                      />
                      <Route
                        path='build'
                        element={
                          <RouteBoundary>
                            <BuildPage />
                          </RouteBoundary>
                        }
                      />
                      <Route
                        path='about'
                        element={
                          <RouteBoundary>
                            <AboutPage />
                          </RouteBoundary>
                        }
                      />

                      {/* Protected routes */}
                      <Route
                        path='profile'
                        element={
                          <ProtectedRoute>
                            <RouteBoundary>
                              <ProfilePage />
                            </RouteBoundary>
                          </ProtectedRoute>
                        }
                      />
                      <Route
                        path='endpoints'
                        element={
                          <ProtectedRoute>
                            <RouteBoundary>
                              <EndpointsPage />
                            </RouteBoundary>
                          </ProtectedRoute>
                        }
                      />

                      {/* Agent session: /agent/:owner/:slug */}
                      <Route
                        path='agent/:owner/:slug'
                        element={
                          <RouteBoundary>
                            <AgentPage />
                          </RouteBoundary>
                        }
                      />

                      {/* GitHub-style endpoint URLs: /:username/:slug */}
                      <Route
                        path=':username/:slug'
                        element={
                          <RouteBoundary>
                            <EndpointDetailPage />
                          </RouteBoundary>
                        }
                      />

                      {/* 404 Not Found */}
                      <Route path='*' element={<NotFoundPage />} />
                    </Route>
                  </Routes>
                </BrowserRouter>
              </AccountingProvider>
            </AuthProvider>
          </GoogleOAuthWrapper>
        </RootProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
