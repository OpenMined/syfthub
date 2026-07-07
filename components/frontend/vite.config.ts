/* eslint-disable unicorn/prefer-string-replace-all */

import path from 'node:path';

import react from '@vitejs/plugin-react-swc';
import { defineConfig } from 'vite';

import config from './_config';

// Serve the static /hi landing prototype, preserving any query string
// (e.g. UTM params) so the page can still read them on submit.
function rewriteHiRoute(
  req: { url?: string },
  _res: unknown,
  next: () => void,
): void {
  if (req.url) {
    const [pathname, query] = req.url.split('?');
    if (pathname === '/hi' || pathname === '/hi/') {
      req.url = '/hi/index.html' + (query ? '?' + query : '');
    }
  }
  next();
}

// https://vitejs.dev/config/
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  plugins: [
    react(),
    {
      name: 'hi-route-rewrite',
      configureServer(server) {
        server.middlewares.use(rewriteHiRoute);
      },
      configurePreviewServer(server) {
        server.middlewares.use(rewriteHiRoute);
      },
    },
    {
      name: 'dynamic-html',
      transformIndexHtml(html) {
        return html
          .replace(/%TITLE%/g, config.metadata.title)
          .replace(/%DESCRIPTION%/g, config.metadata.description)
          .replace(/%KEYWORDS%/g, config.metadata.keywords)
          .replace(/%OG_IMAGE%/g, config.metadata.ogImage);
      }
    }
  ],
  server: {
    host: config.server.host,
    port: config.server.port,
    watch: {
      // Use polling for Docker bind mounts where inotify events may not propagate
      usePolling: true,
      interval: 1000,
    },
  },
  preview: {
    host: config.server.host,
    port: config.server.port,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  }
});
