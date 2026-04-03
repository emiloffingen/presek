import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import { useNewsStore } from '@/store/useNewsStore';
import { NewsFeed } from './components/news/NewsFeed';
import { FrontendV2 } from './pages/FrontendV2';
import { Briefing } from './pages/Briefing';
import { Stats } from './pages/Stats';
import { ClusterDetail } from './pages/ClusterDetail';
import { useSSE } from './hooks/useSSE';

// Bridge to allow non-React code (like the legacy nav) to trigger React Router transitions
const NavigationBridge: React.FC = () => {
  const navigate = useNavigate();
  useEffect(() => {
    (window as any).presekNavigate = (path: string) => {
      navigate(path);
    };
    return () => { delete (window as any).presekNavigate; };
  }, [navigate]);
  return null;
};

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
    <>
      <NavigationBridge />
      <Routes>
        <Route path="/" element={<FrontendV2 />} />
        <Route path="/legacy" element={<NewsFeed />} />
        <Route path="/saved" element={<NewsFeed />} />
        <Route path="/briefing" element={<Briefing />} />
        <Route path="/stats" element={<Stats />} />
        <Route path="/cluster/:id" element={<ClusterDetail />} />
      </Routes>
    </>
  );
};

export const App: React.FC = () => {
  return (
    <Router>
      <AppContent />
    </Router>
  );
};
