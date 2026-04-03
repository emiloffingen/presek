import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { HomePage } from './pages/HomePage';
import { ClusterDetailPage } from './pages/ClusterDetailPage';
import { StatsPage } from './pages/StatsPage';
import { BriefingPage } from './pages/BriefingPage';
import { SavedPage } from './pages/SavedPage';

function App() {
  // Apply saved theme on mount
  useEffect(() => {
    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (saved === 'dark' || (!saved && prefersDark)) {
      document.documentElement.classList.add('dark');
    }
  }, []);

  return (
    <Router>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/cluster/:clusterId" element={<ClusterDetailPage />} />
        <Route path="/stats" element={<StatsPage />} />
        <Route path="/briefing" element={<BriefingPage />} />
        <Route path="/saved" element={<SavedPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
