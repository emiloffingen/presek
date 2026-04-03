import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { TrendingSidebar } from './components/layout/TrendingSidebar';
import { PulseTicker } from './components/layout/PulseTicker';
import { useNewsStore } from './store/useNewsStore';
import { Cluster } from './types';
import * as ui from './utils/ui-init';

// Hydration Logic
const hydrateStore = () => {
  const initialStateElement = document.getElementById('initial-state');
  if (initialStateElement) {
    try {
      const { clusters, trending } = JSON.parse(initialStateElement.textContent || '{"clusters":[], "trending":[]}');
      const store = useNewsStore.getState();
      if (clusters && clusters.length > 0) {
        store.setClusters(clusters);
        console.log('Presek React: Hydrated clusters.');
      }
      if (trending && trending.length > 0) {
        store.setTrending(trending);
        console.log('Presek React: Hydrated trending.');
      }
    } catch (e) {
      console.error('Presek React: Hydration failed:', e);
    }
  }
};

const init = () => {
  try {
    // Global UI initialization
    ui.initTheme();
    ui.setupThemeEvents();
    ui.initNavigation();
    ui.updateMacedonianDate();
    ui.setupLinkInterception();
  } catch (e) {
    console.error('Presek UI Init failed:', e);
  }

  const mountRoot = (id: string, Component: React.ReactElement) => {
    const el = document.getElementById(id);
    if (!el) return;
    try {
      ReactDOM.createRoot(el).render(<React.StrictMode>{Component}</React.StrictMode>);
    } catch (e) {
      console.error(`Mounting ${id} failed:`, e);
    }
  };

  hydrateStore();
  mountRoot('pageWrap', <App />);
  mountRoot('sidebarTrending', <TrendingSidebar />);
  mountRoot('entityPulse', <PulseTicker />);
};

// Start the app
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
