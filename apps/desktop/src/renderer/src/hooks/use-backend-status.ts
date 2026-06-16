import { useEffect, useState } from 'react';
import type {
  BackendPollingError,
  BackendStatusResponse,
  BackendStatusV2,
} from '../../../preload/types';

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
  const [pollingError, setPollingError] = useState<BackendPollingError | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    window.electronAPI.backends.getStatus().then((s) => {
      setStatuses(s);
      setLoaded(true);
    });
    window.electronAPI.backends.getPollingError().then(setPollingError);

    const unsubStatus = window.electronAPI.backends.onStatusChanged((s) => {
      setStatuses(s);
      setLoaded(true);
    });
    const unsubPollingError = window.electronAPI.backends.onPollingError(setPollingError);

    return () => {
      unsubStatus();
      unsubPollingError();
    };
  }, []);

  const refresh = async (): Promise<BackendStatusResponse> => {
    const next = await window.electronAPI.backends.refresh();
    setStatuses(next);
    setLoaded(true);
    return next;
  };

  return { statuses, pollingError, loaded, refresh };
}
