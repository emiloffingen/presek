import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { useNewsStore } from '@/store/useNewsStore';
import { NewsFeed } from './components/news/NewsFeed';
import { Briefing } from './pages/Briefing';
import { Stats } from './pages/Stats';
import { ClusterDetail } from './pages/ClusterDetail';
import { useSSE } from './hooks/useSSE';

const AppContent: React.FC = () => {
  const location = useLocation();
  const { setFilter } = useNewsStore();
  
  useSSE();

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    setFilter({
      topic: params.get('topic') || '',
      query: params.get('q') || '',
      isSaved: location.pathname === '/saved'
    });
  }, [location, setFilter]);

  return (
    <Routes>
      <Route path="/" element={<NewsFeed />} />
      <Route path="/saved" element={<NewsFeed />} />
      <Route path="/briefing" element={<Briefing />} />
      <Route path="/stats" element={<Stats />} />
      <Route path="/cluster/:id" element={<ClusterDetail />} />
    </Routes>
  );
};

export const App: React.FC = () => {
  return (
    <Router>
      <AppContent />
    </Router>
  );
};
