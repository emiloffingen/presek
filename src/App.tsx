import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { HomePage } from './pages/HomePage';
import { ClusterDetailPage } from './pages/ClusterDetailPage';
import { StatsPage } from './pages/StatsPage';
import { BriefingPage } from './pages/BriefingPage';
import { useTheme } from './hooks/useTheme';

function App() {
  const { theme } = useTheme();

  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [theme]);

  return (
    <Router>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/cluster/:clusterId" element={<ClusterDetailPage />} />
        <Route path="/stats" element={<StatsPage />} />
        <Route path="/briefing" element={<BriefingPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
