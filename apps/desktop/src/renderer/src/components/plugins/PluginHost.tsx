import { useState, useEffect, Suspense, Component, type ReactNode } from 'react';
import { loadPlugin } from '@/federation/loader';
import type { PluginComponent, PluginHostProps } from '@/federation/types';

interface ErrorBoundaryProps {
  pluginId: string;
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

class PluginErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
          <h3 className="text-sm font-medium text-destructive">
            Plugin &quot;{this.props.pluginId}&quot; crashed
          </h3>
          <pre className="mt-2 max-h-32 overflow-auto font-mono text-xs text-muted-foreground">
            {this.state.error.message}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

interface PluginHostComponentProps extends PluginHostProps {
  pluginId: string;
  exposedModule: string;
}

function PluginLoader({ pluginId, exposedModule, ...props }: PluginHostComponentProps) {
  const [Comp, setComp] = useState<PluginComponent | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadPlugin(pluginId, exposedModule)
      .then((c) => setComp(() => c))
      .catch((err) => setError(err.message));
  }, [pluginId, exposedModule]);

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
        <h3 className="text-sm font-medium text-destructive">Failed to load plugin</h3>
        <p className="mt-1 text-xs text-muted-foreground">{error}</p>
      </div>
    );
  }

  if (!Comp) {
    return (
      <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
        Loading plugin...
      </div>
    );
  }

  return <Comp {...props} />;
}

export function PluginHost(props: PluginHostComponentProps) {
  return (
    <PluginErrorBoundary pluginId={props.pluginId}>
      <Suspense
        fallback={
          <div className="p-6 text-sm text-muted-foreground">Loading plugin...</div>
        }
      >
        <PluginLoader {...props} />
      </Suspense>
    </PluginErrorBoundary>
  );
}
