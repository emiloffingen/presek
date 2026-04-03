import React from 'react';

interface SkeletonProps {
  count?: number;
}

export const Skeleton: React.FC<SkeletonProps> = ({ count = 1 }) => {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="news-cluster skeleton-card span-3">
          <div className="skeleton-box" style={{ width: '100%', aspectRatio: '16/9', marginBottom: '1rem' }}></div>
          <div className="skeleton-box" style={{ width: '80%', height: '1.5rem', marginBottom: '0.5rem' }}></div>
          <div className="skeleton-box" style={{ width: '60%', height: '1rem' }}></div>
        </div>
      ))}
    </>
  );
};
