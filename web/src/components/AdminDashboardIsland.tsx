import React from 'react';
import AdminDashboard from './AdminDashboard';
import { ErrorBoundary } from './ui/ErrorBoundary';

const AdminDashboardIsland: React.FC<{ lang?: string }> = ({ lang = 'mk' }) => (
  <ErrorBoundary lang={lang}>
    <AdminDashboard lang={lang} />
  </ErrorBoundary>
);

export default AdminDashboardIsland;
