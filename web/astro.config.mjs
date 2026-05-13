// @ts-check
import { defineConfig } from 'astro/config';

import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import node from '@astrojs/node';
import partytown from '@astrojs/partytown';

// ⚠️ SERBIAN SITE - presek.live - DO NOT EDIT for Macedonian
// https://astro.build/config
export default defineConfig({
  site: 'https://presek.live',
  trailingSlash: 'never',
  output: 'server',
  prefetch: {
    prefetchAll: false,
    defaultStrategy: 'viewport',
  },
  integrations: [
    react(), 
    sitemap(),
    partytown({
      config: {
        forward: ['dataLayer.push', 'gtag'],
      },
    }),
  ],

  vite: {
    plugins: [tailwindcss()]
  },

  adapter: node({
    mode: 'standalone'
  })
});