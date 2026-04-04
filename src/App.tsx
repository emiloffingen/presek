import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { HomePage } from './pages/HomePage';

const ClusterDetailPage = lazy(() =>
  import('./pages/ClusterDetailPage').then((module) => ({ default: module.ClusterDetailPage }))
);
const StatsPage = lazy(() =>
  import('./pages/StatsPage').then((module) => ({ default: module.StatsPage }))
);
const BriefingPage = lazy(() =>
  import('./pages/BriefingPage').then((module) => ({ default: module.BriefingPage }))
);
const SavedPage = lazy(() =>
  import('./pages/SavedPage').then((module) => ({ default: module.SavedPage }))
);
const IzvoriPage = lazy(() =>
  import('./pages/IzvoriPage').then((module) => ({ default: module.IzvoriPage }))
);
const ArchivePage = lazy(() =>
  import('./pages/ArchivePage').then((module) => ({ default: module.ArchivePage }))
);

function RouteFallback() {
  return (
    <div className="min-h-screen bg-primary">
      <div className="page-container py-16">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-muted">
          Вчитување...
        </p>
      </div>
    </div>
  );
}

function App() {
  return (
    <Router>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/cluster/:clusterId" element={<ClusterDetailPage />} />
          <Route path="/stats" element={<StatsPage />} />
          <Route path="/briefing" element={<BriefingPage />} />
          <Route path="/saved" element={<SavedPage />} />
          <Route path="/izvori" element={<IzvoriPage />} />
          <Route path="/arhiva" element={<ArchivePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Router>
  );
}

export default App;
