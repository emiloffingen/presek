import React from 'react';

interface Props {
  children: React.ReactNode;
  lang?: string;
}

export class ErrorBoundary extends React.Component<Props, { hasError: boolean }> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: any) {
    return { hasError: true };
  }

  componentDidCatch(error: any, errorInfo: any) {
    console.error("Island crashed:", error, errorInfo);
    try {
      const reportUrl = import.meta.env.PUBLIC_ERROR_REPORT_URL as string | undefined;
      if (reportUrl && typeof fetch === 'function') {
        fetch(reportUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          keepalive: true,
          body: JSON.stringify({
            message: String(error?.message || error),
            stack: String(error?.stack || ''),
            componentStack: String(errorInfo?.componentStack || ''),
            url: typeof location !== 'undefined' ? location.href : '',
            ts: Date.now(),
          }),
        }).catch(() => {});
      }
    } catch {
      /* reporting must never throw */
    }
  }

  render() {
    const { lang = 'mk' } = this.props;
    if (this.state.hasError) {
      return (
        <div className="p-4 border border-red-200 bg-red-50 rounded-none text-red-800 text-xs text-center">
          <p>{lang === 'sr' ? 'Došlo je do greške. Pokušajte ponovo.' : 'Се појави грешка. Обидете се повторно.'}</p>
          <button onClick={() => this.setState({ hasError: false })} className="mt-2 font-bold underline">{lang === 'sr' ? 'Restartuj' : 'Рестартирај'}</button>
        </div>
      );
    }
    return this.props.children;
  }
}
