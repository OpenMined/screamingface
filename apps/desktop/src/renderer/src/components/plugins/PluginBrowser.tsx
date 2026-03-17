import { useState } from 'react';
import { Download } from 'lucide-react';

interface PluginBrowserProps {
  onInstall: (url: string) => Promise<void>;
}

export function PluginBrowser({ onInstall }: PluginBrowserProps) {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleInstall = async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError('');
    try {
      await onInstall(url.trim());
      setUrl('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to install plugin');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="text-sm font-medium text-foreground">Install Plugin</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Paste a remote entry URL to load a plugin from CDN.
      </p>
      <div className="mt-3 flex gap-2">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleInstall()}
          placeholder="https://cdn.example.com/plugin/remoteEntry.json"
          className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <button
          onClick={handleInstall}
          disabled={loading || !url.trim()}
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          <Download className="h-3.5 w-3.5" />
          {loading ? 'Installing...' : 'Install'}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </div>
  );
}
