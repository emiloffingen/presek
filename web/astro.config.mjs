// @ts-nocheck
import { defineConfig } from 'astro/config';

import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import node from '@astrojs/node';

// Site URL is determined dynamically in Layout.astro based on language
// https://astro.build/config
export default defineConfig({
  site: import.meta.env.PUBLIC_SITE_URL || 'https://presek.live',
  trailingSlash: 'never',
  output: 'server',
  i18n: {
    defaultLocale: 'sr',
    locales: ['sr', 'mk'],
    routing: {
      prefixDefaultLocale: false
    }
  },
  prefetch: {
    prefetchAll: false,
    defaultStrategy: 'viewport',
  },
  integrations: [
    react(),
    sitemap(),
  ],

  vite: {
    plugins: [tailwindcss()]
  },

  adapter: node({
    mode: 'standalone'
  }),

  // Hash-based CSP for Astro islands + inline page scripts (middleware only adds frame-ancestors).
  security: {
    csp: {
      directives: [
        "default-src 'self'",
        "font-src 'self' data:",
        "img-src 'self' data: https: blob: https://www.google-analytics.com https://www.googletagmanager.com",
        "connect-src 'self' https: wss: https://www.google-analytics.com https://analytics.google.com https://www.googletagmanager.com",
        "frame-src 'self'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
        "media-src 'self' data: https:",
        "worker-src 'self'",
      ],
      scriptDirective: {
        resources: ["'self'", 'https://www.googletagmanager.com'],
        strictDynamic: true,
      },
    },
  },
});
