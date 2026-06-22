// apps/desktop/src/renderer/src/hooks/use-scoreboard-url.ts
//
// Resolves the public scoreboard URL the same way publishing does (env →
// sf.json → production default; SF-271 set the default in publish-context).
// The renderer can't read env/config itself, so it asks the main process via
// publish.getContext(). Returns null until resolved.

import { useEffect, useState } from 'react';

export function useScoreboardUrl(): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void window.electronAPI.publish.getContext().then((ctx) => {
      if (active) setUrl(ctx.scoreboardUrl);
    });
    return () => {
      active = false;
    };
  }, []);

  return url;
}
