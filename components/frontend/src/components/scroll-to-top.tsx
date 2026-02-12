import { useEffect } from 'react';

import { useLocation } from 'react-router-dom';

/**
 * ScrollToTop - Scrolls to the top of the page on route changes.
 *
 * This component fixes the common SPA issue where navigation between
 * pages doesn't reset the scroll position. Place inside BrowserRouter.
 */
export function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
}
