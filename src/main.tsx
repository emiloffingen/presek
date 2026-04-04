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
