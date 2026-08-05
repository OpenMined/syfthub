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

// crypto.randomUUID only exists in secure contexts, so it is missing when the
// dev server is reached over plain http on a non-localhost host (docker
// hostname, LAN IP, tunnel). Polyfill it in dev only — production is https.
const DEV_RANDOM_UUID_POLYFILL = `
if (globalThis.crypto && !crypto.randomUUID) {
  crypto.randomUUID = () => {
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 15) | 64;
    b[8] = (b[8] & 63) | 128;
    const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
  };
}
`;

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
      name: 'dev-crypto-randomuuid-polyfill',
      apply: 'serve',
      transformIndexHtml() {
        return [
          {
            tag: 'script',
            injectTo: 'head-prepend',
            children: DEV_RANDOM_UUID_POLYFILL,
          },
        ];
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
    // Explicit allow-list (not `true`) keeps Vite's DNS-rebinding protection.
    // `.localhost` covers every *.localhost dev hostname (station tenants,
    // syfthub.localhost, …); host.k3d.internal is the hub as seen from k3d.
    allowedHosts: ['.localhost', 'host.k3d.internal'],
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
