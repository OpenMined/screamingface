import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './globals.css';

interface RendererErrorBoundaryState {
  error: Error | null;
}

class RendererErrorBoundary extends Component<{ children: ReactNode }, RendererErrorBoundaryState> {
  state: RendererErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[renderer] root render failed:', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-screen items-center justify-center bg-background p-6 text-foreground">
          <div className="max-w-xl rounded-lg border border-destructive/50 bg-card p-5 shadow-lg">
            <p className="font-heading text-sm font-semibold text-destructive">
              ScreamingFace failed to render
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              Check the desktop debug log for renderer console details.
            </p>
            <pre className="mt-4 max-h-64 overflow-auto whitespace-pre-wrap rounded border border-border bg-background p-3 text-[11px] text-muted-foreground">
              {this.state.error.stack || this.state.error.message}
            </pre>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Missing #root element');
}

console.info('[renderer] mounting React root');

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <RendererErrorBoundary>
      <App />
    </RendererErrorBoundary>
  </React.StrictMode>,
);
