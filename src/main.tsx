import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { TrendingSidebar } from './components/layout/TrendingSidebar';
import { PulseTicker } from './components/layout/PulseTicker';
import { useNewsStore } from './store/useNewsStore';
import { Cluster } from './types';
import { initNavigation } from './js/modules/navigation';
import { initTheme, setupThemeEvents } from './js/modules/theme';
import { _updateMacedonianDate } from './js/modules/utils';

// Intercept clicks on links from SSR templates to use React Router navigation
const setupLinkInterception = () => {
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    const anchor = target.closest('a') as HTMLAnchorElement | null;
    if (anchor && anchor.href && anchor.href.startsWith(window.location.origin)) {
      const path = anchor.getAttribute('href');
      // Only intercept internal paths that we have React routes for
      const isReactRoute = path && (
        path === '/' || 
        path === '/saved' || 
        path === '/briefing' || 
        path === '/stats' || 
        path.startsWith('/cluster/')
      );

      if (isReactRoute && anchor.target !== '_blank') {
        e.preventDefault();
        window.history.pushState({}, '', path);
        window.dispatchEvent(new PopStateEvent('popstate'));
      }
    }
  });
};

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
    // Legacy UI initialization
    initTheme();
    setupThemeEvents();
    initNavigation();
    _updateMacedonianDate();
    setupLinkInterception();
  } catch (e) {
    console.error('Legacy init failed:', e);
  }

  const mountRoot = (id: string, Component: React.ReactElement, useHydrate = false) => {
    const el = document.getElementById(id);
    if (!el) return;
    try {
      if (useHydrate) {
        // We use createRoot instead of hydrateRoot for now to avoid mismatch crashes
        ReactDOM.createRoot(el).render(<React.StrictMode>{Component}</React.StrictMode>);
      } else {
        ReactDOM.createRoot(el).render(<React.StrictMode>{Component}</React.StrictMode>);
      }
    } catch (e) {
      console.error(`Mounting ${id} failed:`, e);
    }
  };

  hydrateStore();
  mountRoot('pageWrap', <App />, true);
  mountRoot('sidebarTrending', <TrendingSidebar />);
  mountRoot('entityPulse', <PulseTicker />);
};

// Start the app
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
