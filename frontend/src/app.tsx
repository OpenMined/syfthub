import { lazy } from 'react';

import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { ProtectedRoute } from './components/auth/protected-route';
import RootProvider from './components/providers/root';
import { ScrollToTop } from './components/scroll-to-top';
import { AccountingProvider } from './context/accounting-context';
import { AuthProvider } from './context/auth-context';
import { MainLayout } from './layouts/main-layout';
import { ErrorBoundary } from './observability';

// Lazy load all pages for code splitting
const HomePage = lazy(() => import('./pages/home'));
const BrowsePage = lazy(() => import('./pages/browse'));
const ChatPage = lazy(() => import('./pages/chat'));
const BuildPage = lazy(() => import('./pages/build'));
const AboutPage = lazy(() => import('./pages/about'));
const ProfilePage = lazy(() => import('./pages/profile'));
const EndpointsPage = lazy(() => import('./pages/endpoints'));
const EndpointDetailPage = lazy(() => import('./pages/endpoint-detail'));
const NotFoundPage = lazy(() => import('./pages/not-found'));

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
 * - Suspense boundary for lazy loading
 */
export default function App() {
  return (
    <ErrorBoundary>
      <RootProvider>
        <AuthProvider>
          <AccountingProvider>
            <BrowserRouter>
              <ScrollToTop />
              <Routes>
                <Route element={<MainLayout />}>
                  {/* Public routes */}
                  <Route index element={<HomePage />} />
                  <Route path='browse' element={<BrowsePage />} />
                  <Route path='chat' element={<ChatPage />} />
                  <Route path='build' element={<BuildPage />} />
                  <Route path='about' element={<AboutPage />} />

                  {/* Protected routes */}
                  <Route
                    path='profile'
                    element={
                      <ProtectedRoute>
                        <ProfilePage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path='endpoints'
                    element={
                      <ProtectedRoute>
                        <EndpointsPage />
                      </ProtectedRoute>
                    }
                  />

                  {/* GitHub-style endpoint URLs: /:username/:slug */}
                  <Route path=':username/:slug' element={<EndpointDetailPage />} />

                  {/* 404 Not Found */}
                  <Route path='*' element={<NotFoundPage />} />
                </Route>
              </Routes>
            </BrowserRouter>
          </AccountingProvider>
        </AuthProvider>
      </RootProvider>
    </ErrorBoundary>
  );
}
