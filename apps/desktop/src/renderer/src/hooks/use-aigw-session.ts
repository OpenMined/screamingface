import { useCallback, useEffect, useState } from 'react';
import type { AigwLoginResult, AigwSessionSnapshot } from '../../../preload/types';

const initialSnapshot: AigwSessionSnapshot = {
  hasValidJwt: false,
  jwtExpiresAt: null,
  isLoggedIn: false,
  username: null,
  gatewayUrl: 'http://127.0.0.1:9105',
  rememberAvailable: true,
  storedInPlaintext: false,
  lastError: null,
};

export function useAigwSession() {
  const [snapshot, setSnapshot] = useState<AigwSessionSnapshot>(initialSnapshot);
  const [jwt, setJwt] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [expiredNonce, setExpiredNonce] = useState(0);

  useEffect(() => {
    let mounted = true;
    window.electronAPI.aigwSession.getState().then((state) => {
      if (!mounted) return;
      setSnapshot(state);
      setLoaded(true);
    });
    const unsubChanged = window.electronAPI.aigwSession.onChanged((state) => {
      setSnapshot(state);
      if (!state.hasValidJwt) setJwt(null);
    });
    const unsubExpired = window.electronAPI.aigwSession.onExpired((state) => {
      setSnapshot(state);
      setJwt(null);
      setExpiredNonce((value) => value + 1);
    });
    return () => {
      mounted = false;
      unsubChanged();
      unsubExpired();
    };
  }, []);

  const getJwt = useCallback(async () => {
    const nextJwt = await window.electronAPI.aigwSession.getJwt();
    setJwt(nextJwt);
    return nextJwt;
  }, []);

  const login = useCallback(
    async (
      username: string,
      password: string,
      options?: { persist?: boolean },
    ): Promise<AigwLoginResult> => {
      const result = await window.electronAPI.aigwSession.login(username, password, options);
      setSnapshot(result.snapshot);
      if (!result.ok) setJwt(null);
      return result;
    },
    [],
  );

  const logout = useCallback(async () => {
    const state = await window.electronAPI.aigwSession.logout();
    setSnapshot(state);
    setJwt(null);
    return state;
  }, []);

  const setGatewayUrl = useCallback(async (gatewayUrl: string) => {
    const state = await window.electronAPI.aigwSession.setGatewayUrl(gatewayUrl);
    setSnapshot(state);
    setJwt(null);
    return state;
  }, []);

  return {
    ...snapshot,
    jwt,
    loaded,
    expiredNonce,
    getJwt,
    login,
    logout,
    setGatewayUrl,
  };
}

export type AigwSessionController = ReturnType<typeof useAigwSession>;
