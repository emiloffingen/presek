// @ts-check
import { defineConfig } from 'astro/config';

import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';
import node from '@astrojs/node';

// https://astro.build/config
export default defineConfig({
  site: 'https://presek.live',
  output: 'server',
  prefetch: {
    prefetchAll: false,
    defaultStrategy: 'hover',
  },
  integrations: [react(), sitemap()],

  vite: {
    plugins: [tailwindcss()]
  },

  adapter: node({
    mode: 'standalone'
  })
});