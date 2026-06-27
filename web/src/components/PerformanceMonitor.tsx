import React, { useEffect, useRef } from 'react';

interface PerformanceMonitorProps {
  componentName: string;
  enabled?: boolean;
}

export const PerformanceMonitor: React.FC<PerformanceMonitorProps> = ({ 
  componentName, 
  enabled = true 
}) => {
  const renderCount = useRef(0);
  const mountTime = useRef(0);

  useEffect(() => {
    if (!enabled || typeof window === 'undefined') return;

    renderCount.current++;
    
    if (renderCount.current === 1) {
      // First render (mount)
      mountTime.current = performance.now();
      console.info(`[PERF] ${componentName} mounted`);
    } else {
      // Subsequent renders (updates)
      const now = performance.now();
      const timeSinceMount = now - mountTime.current;
      console.info(`[PERF] ${componentName} re-render #${renderCount.current} (${timeSinceMount.toFixed(2)}ms since mount)`);
    }

    return () => {
      if (renderCount.current === 1) {
        const unmountTime = performance.now();
        const lifetime = unmountTime - mountTime.current;
        console.info(`[PERF] ${componentName} unmounted after ${lifetime.toFixed(2)}ms`);
      }
    };
  }, [componentName, enabled]);

  return null;
};

export const usePerformanceMonitor = (componentName: string, enabled = true) => {
  // Hook version for functional components
  PerformanceMonitor({ componentName, enabled });
};