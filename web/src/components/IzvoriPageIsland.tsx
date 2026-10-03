import React from 'react';
import IzvoriPage from './IzvoriPage';
import { ErrorBoundary } from './ui/ErrorBoundary';
import type { ui } from '../i18n/ui';

const IzvoriPageIsland: React.FC<{ lang?: keyof typeof ui }> = ({ lang = 'mk' }) => (
  <ErrorBoundary lang={lang}>
    <IzvoriPage lang={lang} />
  </ErrorBoundary>
);

export default IzvoriPageIsland;
