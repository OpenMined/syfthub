import { GoogleOAuthProvider } from '@react-oauth/google';
import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { ProtectedRoute } from './components/auth/protected-route';
import { RoleBasedRoute } from './components/auth/role-based-route';
import RootProvider from './components/providers/root';
import { RouteBoundary } from './components/route-boundary';
import { ScrollToTop } from './components/scroll-to-top';
import { AuthProvider } from './context/auth-context';
import { TempoWalletProvider } from './context/tempo-wallet-context';
import { WalletProvider } from './context/wallet-context';
import { MainLayout } from './layouts/main-layout';
import { lazyWithRetry } from './lib/lazy-with-retry';
import { queryClient } from './lib/query-client';
import { getGoogleClientId } from './lib/sdk-client';
import { ErrorBoundary } from './observability';

// Get Google OAuth Client ID from environment
const googleClientId = getGoogleClientId();

// Lazy load all pages for code splitting (with auto-reload on stale chunks)
const CLISetupPage = lazyWithRetry(() => import('./pages/cli-setup'));
const HomePage = lazyWithRetry(() => import('./pages/home'));
const BrowsePage = lazyWithRetry(() => import('./pages/browse'));
const ChatPage = lazyWithRetry(() => import('./pages/chat'));
const BuildPage = lazyWithRetry(() => import('./pages/build'));
const AboutPage = lazyWithRetry(() => import('./pages/about'));
const ProfilePage = lazyWithRetry(() => import('./pages/profile'));
const EndpointsPage = lazyWithRetry(() => import('./pages/endpoints'));
const EndpointDetailPage = lazyWithRetry(() => import('./pages/endpoint-detail'));
const UserProfilePage = lazyWithRetry(() => import('./pages/user-profile'));
const CollectivesPage = lazyWithRetry(() => import('./pages/collectives'));
const CollectiveDetailPage = lazyWithRetry(() => import('./pages/collective-detail'));
const CollectiveAdminPage = lazyWithRetry(() => import('./pages/collective-admin'));
const CreateCollectivePage = lazyWithRetry(() => import('./pages/create-collective'));
const CollectiveInvitationPage = lazyWithRetry(() => import('./pages/collective-invitation'));
const AdminPage = lazyWithRetry(() => import('./pages/admin'));
// TODO(agent-feature): Uncomment when agent endpoint UI is re-enabled
// const AgentPage = lazyWithRetry(() => import('./pages/agent'));
const NotFoundPage = lazyWithRetry(() => import('./pages/not-found'));

/**
 * App - Root application component with routing configuration.
 *
 * Route structure:
 * - / : Home page with hero and recent items
 * - /browse : Browse data sources
 * - /chat : AI chat interface
 * - /build : Developer portal
 * - /profile : User profile (protected)
 * - /join : Endpoint management with onboarding (protected)
 * - /:username/:slug : GitHub-style endpoint detail
 * - * : 404 Not Found
 *
 * Note: /q is handled by nginx (proxied directly to the aggregator).
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
              <TempoWalletProvider>
                <WalletProvider>
                  <BrowserRouter>
                    <ScrollToTop />
                    <Routes>
                      {/* CLI setup — standalone page, no sidebar or navbar */}
                      <Route
                        path='cli-setup'
                        element={
                          <RouteBoundary>
                            <CLISetupPage />
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

                        {/* Collectives — public discovery + protected create/admin */}
                        <Route
                          path='collectives'
                          element={
                            <RouteBoundary>
                              <CollectivesPage />
                            </RouteBoundary>
                          }
                        />
                        {/* Browsing collectives now lives in the unified
                            /browse page as a tab; keep the old path as a
                            redirect for existing links and bookmarks. */}
                        <Route
                          path='collectives/browse'
                          element={<Navigate to='/browse?tab=collectives' replace />}
                        />
                        <Route
                          path='collectives/create'
                          element={
                            <ProtectedRoute>
                              <RouteBoundary>
                                <CreateCollectivePage />
                              </RouteBoundary>
                            </ProtectedRoute>
                          }
                        />
                        {/* Invitation-response landing page linked from the
                            invitation email — auth required so we know who
                            is responding. */}
                        <Route
                          path='collectives/:slug/invitations/:endpointId'
                          element={
                            <ProtectedRoute>
                              <RouteBoundary>
                                <CollectiveInvitationPage />
                              </RouteBoundary>
                            </ProtectedRoute>
                          }
                        />
                        <Route
                          path='c/:slug/admin'
                          element={
                            <ProtectedRoute>
                              <RouteBoundary>
                                <CollectiveAdminPage />
                              </RouteBoundary>
                            </ProtectedRoute>
                          }
                        />
                        <Route
                          path='c/:slug'
                          element={
                            <RouteBoundary>
                              <CollectiveDetailPage />
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
                          path='join'
                          element={
                            <ProtectedRoute>
                              <RouteBoundary>
                                <EndpointsPage />
                              </RouteBoundary>
                            </ProtectedRoute>
                          }
                        />

                        {/* Admin-only dashboard. Must precede the `:username`
                            catch-all so "/admin" isn't read as a username. */}
                        <Route
                          path='admin'
                          element={
                            <ProtectedRoute>
                              <RouteBoundary>
                                <RoleBasedRoute requiredRole='admin'>
                                  <AdminPage />
                                </RoleBasedRoute>
                              </RouteBoundary>
                            </ProtectedRoute>
                          }
                        />

                        {/* TODO(agent-feature): Uncomment route when agent endpoint UI is re-enabled
                        <Route
                          path='agent/:owner/:slug'
                          element={
                            <RouteBoundary>
                              <AgentPage />
                            </RouteBoundary>
                          }
                        />
                        */}

                        {/* GitHub-style endpoint URLs: /:username/:slug */}
                        <Route
                          path=':username/:slug'
                          element={
                            <RouteBoundary>
                              <EndpointDetailPage />
                            </RouteBoundary>
                          }
                        />

                        {/* Public user profile: /:username */}
                        <Route
                          path=':username'
                          element={
                            <RouteBoundary>
                              <UserProfilePage />
                            </RouteBoundary>
                          }
                        />

                        {/* 404 Not Found */}
                        <Route path='*' element={<NotFoundPage />} />
                      </Route>
                    </Routes>
                  </BrowserRouter>
                </WalletProvider>
              </TempoWalletProvider>
            </AuthProvider>
          </GoogleOAuthWrapper>
        </RootProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
