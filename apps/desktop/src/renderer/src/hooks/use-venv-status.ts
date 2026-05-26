import { useState, useEffect, useCallback, useRef } from 'react';
import type { VenvStatus } from '../../../preload/types';

export function useVenvStatus() {
  const [status, setStatus] = useState<VenvStatus>('unknown');
  const [uvFound, setUvFound] = useState(true);
  const [progress, setProgress] = useState<string[]>([]);
  const bootstrapping = useRef(false);

  useEffect(() => {
    window.electronAPI.venv.detect().then((result) => {
      setStatus(result.status);
      setUvFound(result.uvFound);

      // Auto-bootstrap in production: create venv + sync when missing
      if (
        result.autoBootstrap &&
        result.status === 'missing' &&
        result.uvFound &&
        !bootstrapping.current
      ) {
        bootstrapping.current = true;
        window.electronAPI.venv.create().then((ok) => {
          if (ok) window.electronAPI.venv.sync();
          bootstrapping.current = false;
        });
      }

      // Auto re-sync after app update (version stamp mismatch)
      if (result.needsSync && result.status === 'ready') {
        window.electronAPI.venv.sync();
      }
    });

    const unsub1 = window.electronAPI.venv.onStatusChanged((s) => setStatus(s));
    const unsub2 = window.electronAPI.venv.onProgress((line) => {
      setProgress((prev) => {
        const next = [...prev, line];
        return next.length > 200 ? next.slice(-200) : next;
      });
    });

    return () => {
      unsub1();
      unsub2();
    };
  }, []);

  const detect = useCallback(() => window.electronAPI.venv.detect(), []);
  const create = useCallback(() => window.electronAPI.venv.create(), []);
  const sync = useCallback((extra?: string) => window.electronAPI.venv.sync(extra), []);

  return { status, uvFound, progress, detect, create, sync };
}
