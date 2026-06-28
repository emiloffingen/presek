import React, { Suspense, lazy, type ComponentType, useState, useEffect, useRef } from 'react';

interface UseInViewOptions extends IntersectionObserverInit {
  triggerOnce?: boolean;
}

function useInView(options: UseInViewOptions = {}) {
  const [inView, setInView] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }

    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setInView(true);
        if (options.triggerOnce) {
          observer.unobserve(element);
        }
      } else if (!options.triggerOnce) {
        setInView(false);
      }
    }, {
      root: options.root,
      rootMargin: options.rootMargin,
      threshold: options.threshold,
    });

    observer.observe(element);
    return () => {
      if (element) {
        observer.unobserve(element);
      }
    };
  }, [options.threshold, options.rootMargin, options.triggerOnce]);

  return { ref, inView };
}

interface LazyLoadProps {
  component: () => Promise<{ default: ComponentType<any> }>;
  fallback?: React.ReactNode;
  threshold?: number;
  rootMargin?: string;
  triggerOnce?: boolean;
  [key: string]: any;
}

export const LazyLoad: React.FC<LazyLoadProps> = ({
  component,
  fallback = null,
  threshold = 0.1,
  rootMargin = '200px',
  triggerOnce = true,
  ...props
}) => {
  const { ref, inView } = useInView({
    threshold,
    rootMargin,
    triggerOnce,
  });

  const Component = lazy(component);

  return (
    <div ref={ref}>
      {inView ? (
        <Suspense fallback={fallback || <div style={{ minHeight: '200px' }} />}>
          <Component {...props} />
        </Suspense>
      ) : fallback || null}
    </div>
  );
};

// Hook version for more control
export const useLazyLoad = (component: () => Promise<{ default: ComponentType<any> }>, options = {}) => {
  const { ref, inView } = useInView({
    threshold: 0.1,
    rootMargin: '200px',
    triggerOnce: true,
    ...options,
  });

  const Component = lazy(component);

  return {
    ref,
    inView,
    Component,
  };
};

// Predefined fallback for consistent loading states
export const LoadingFallback = ({ height = 200 }) => (
  <div style={{ minHeight: `${height}px`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    <div style={{ width: '40px', height: '40px', border: '3px solid #f3f3f3', borderTop: '3px solid #3498db', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
  </div>
);

// Add spinner animation
if (typeof document !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  `;
  document.head.appendChild(style);
}