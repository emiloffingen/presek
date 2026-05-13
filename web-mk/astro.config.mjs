// @ts-check
import { defineConfig } from 'astro/config';

import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import node from '@astrojs/node';
import partytown from '@astrojs/partytown';

// ⚠️ MACEDONIAN SITE - пресек.мк - DO NOT EDIT for Serbian
// https://astro.build/config
export default defineConfig({
  site: 'https://presek.mk',  // ASCII domain (Cyrillic display: пресек.мк)
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