import React from 'react';
import ClusterMobileFocusIsland from './ClusterMobileFocusIsland';
import { ErrorBoundary } from '../ui/ErrorBoundary';

const ClusterMobileFocusIslandBoundary: React.FC<{ lang?: string }> = ({ lang = 'mk' }) => (
  <ErrorBoundary lang={lang}>
    <ClusterMobileFocusIsland lang={lang} />
  </ErrorBoundary>
);

export default ClusterMobileFocusIslandBoundary;
