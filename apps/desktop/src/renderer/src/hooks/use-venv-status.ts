import { useState, useEffect, useCallback } from 'react';
import type { VenvStatus } from '../../../preload/types';

export function useVenvStatus() {
  const [status, setStatus] = useState<VenvStatus>('unknown');
  const [uvFound, setUvFound] = useState(true);
  const [progress, setProgress] = useState<string[]>([]);

  useEffect(() => {
    window.electronAPI.venv.detect().then((result) => {
      setStatus(result.status);
      setUvFound(result.uvFound);
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
