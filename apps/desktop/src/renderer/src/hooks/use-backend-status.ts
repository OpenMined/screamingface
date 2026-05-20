import { useEffect, useState } from 'react';
import type { BackendStatusResponse, BackendStatusV2 } from '../../../preload/types';

export function isBackendStatusV2(status: BackendStatusResponse): status is BackendStatusV2 {
  return (
    typeof status === 'object' &&
    status !== null &&
    !Array.isArray(status) &&
    (status as { version?: unknown }).version === 2
  );
}

export function useBackendStatus() {
  const [statuses, setStatuses] = useState<BackendStatusResponse>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    window.electronAPI.backends.getStatus().then((s) => {
      setStatuses(s);
      setLoaded(true);
    });

    const unsubStatus = window.electronAPI.backends.onStatusChanged((s) => {
      setStatuses(s);
      setLoaded(true);
    });

    return unsubStatus;
  }, []);

  const refresh = async (): Promise<void> => {
    const next = await window.electronAPI.backends.refresh();
    setStatuses(next);
    setLoaded(true);
  };

  return { statuses, loaded, refresh };
}
