import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

declare global {
  interface Window {
    __INITIAL_DATA__?: {
      clusters: any[];
      trending: any[];
      theme: string;
    };
    __INITIAL_CLUSTER_DATA__?: {
      cluster: any;
    };
    __INITIAL_BRIEFING_DATA__?: any;
    __INITIAL_STATS_DATA__?: any;
    __INITIAL_SOURCES_DATA__?: {
      sources: any[];
      hot_sources: string[];
    };
    __INITIAL_ARCHIVE_DATA__?: any;
  }
}

const rootElement = document.getElementById('root');
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}
