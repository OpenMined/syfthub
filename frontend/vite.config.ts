/* eslint-disable unicorn/prefer-string-replace-all */

import path from 'node:path';

import react from '@vitejs/plugin-react-swc';
import { defineConfig } from 'vite';

import config from './_config';

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
    port: config.server.port
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
