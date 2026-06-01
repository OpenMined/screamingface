import { describe, expect, it, vi } from 'vitest';

const electronMocks = vi.hoisted(() => ({
  app: {
    getAppPath: vi.fn(() => '/repo/apps/desktop'),
    getPath: vi.fn(() => '/tmp/sf-user-data'),
  },
  dialog: {
    showErrorBox: vi.fn(),
  },
  safeStorage: {
    decryptString: vi.fn(),
    encryptString: vi.fn(),
    isEncryptionAvailable: vi.fn(),
  },
}));

vi.mock('electron', () => electronMocks);
vi.mock('@electron-toolkit/utils', () => ({ is: { dev: true } }));

import { AigwSessionService, type AigwCredentials } from '../aigw-session';

interface RequestRecord {
  url: string;
  init?: { method?: string; headers?: Record<string, string>; body?: string };
}

function cloneConfig(value: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(value)) as Record<string, unknown>;
}

function makeConfig(initial: Record<string, unknown>) {
  let current = cloneConfig(initial);
  return {
    store: {
      read: vi.fn(() => cloneConfig(current)),
      write: vi.fn((next: Record<string, unknown>) => {
        current = cloneConfig(next);
      }),
    },
    current: () => cloneConfig(current),
  };
}

function makeSafeStorage(encryptionAvailable = true) {
  return {
    decryptString: vi.fn((encrypted: Buffer) => encrypted.toString().replace(/^enc:/, '')),
    encryptString: vi.fn((plainText: string) => Buffer.from(`enc:${plainText}`)),
    isEncryptionAvailable: vi.fn(() => encryptionAvailable),
  };
}

function makeRequestJson(tokens: Array<{ token: string; expiresAt: string }>) {
  const requests: RequestRecord[] = [];
  const requestJson = vi.fn(async (url: string, init?: RequestRecord['init']) => {
    requests.push({ url, init });
    if (url.endsWith('/aigateway/session/logout')) {
      return { status: 200, body: '{"authenticated":false}', json: { authenticated: false } };
    }
    const next = tokens.shift();
    if (!next) return { status: 401, body: '{"detail":{"message":"invalid"}}', json: {} };
    const body = { authenticated: true, token: next.token, expires_at: next.expiresAt };
    return { status: 200, body: JSON.stringify(body), json: body };
  });
  return { requestJson, requests };
}

function aigwBase(config: Record<string, unknown>): Record<string, unknown> {
  const pluginConfig = config.plugin_config as Record<string, unknown>;
  return pluginConfig['aigw-base'] as Record<string, unknown>;
}

function makeService(options: {
  config: ReturnType<typeof makeConfig>;
  safeStorage?: ReturnType<typeof makeSafeStorage>;
  requestJson?: ReturnType<typeof makeRequestJson>['requestJson'];
  now?: Date;
}) {
  return new AigwSessionService({
    config: options.config.store,
    safeStorage: options.safeStorage ?? makeSafeStorage(),
    requestJson: options.requestJson ?? makeRequestJson([]).requestJson,
    desktopSecretHeader: () => ({ 'X-SF-Desktop-Secret': 'desktop-secret' }),
    now: () => options.now ?? new Date('2026-01-01T00:00:00.000Z'),
  });
}

describe('AigwSessionService', () => {
  it('logs in through the SF bridge, keeps JWT in memory, and encrypts stored credentials', async () => {
    const config = makeConfig({
      plugin_config: { 'aigw-base': { gateway_url: 'http://gateway' } },
    });
    const safeStorage = makeSafeStorage(true);
    const { requestJson, requests } = makeRequestJson([
      { token: 'jwt-1', expiresAt: '2026-01-01T01:00:00.000Z' },
    ]);
    const service = makeService({ config, safeStorage, requestJson });
    const changed: unknown[] = [];
    service.on('changed', (snapshot) => changed.push(snapshot));

    await service.init();
    await service.setServerUrl('https://127.0.0.1:8000/');
    const result = await service.login({ username: 'admin', password: 'test123' });

    expect(result.ok).toBe(true);
    expect(result.snapshot).not.toHaveProperty('jwt');
    expect(await service.getJwt()).toBe('jwt-1');
    expect(requests[0]).toMatchObject({
      url: 'https://127.0.0.1:8000/aigateway/session/login',
      init: {
        method: 'POST',
        headers: { 'X-SF-Desktop-Secret': 'desktop-secret', 'content-type': 'application/json' },
        body: JSON.stringify({
          username: 'admin',
          password: 'test123',
          gateway_url: 'http://gateway',
        }),
      },
    });
    expect(aigwBase(config.current())).toMatchObject({
      aigw_credentials_username: 'admin',
      aigw_credentials_enc: Buffer.from('enc:test123').toString('base64'),
      aigw_credentials_storage: 'safeStorage',
    });
    expect(aigwBase(config.current())).not.toHaveProperty('aigw_credentials_plaintext');
    expect(changed.every((snapshot) => !Object.hasOwn(snapshot as object, 'jwt'))).toBe(true);
  });

  it('loads encrypted credentials and silently logs in when the SF server URL becomes available', async () => {
    const config = makeConfig({
      plugin_config: {
        'aigw-base': {
          gateway_url: 'http://gateway',
          aigw_credentials_username: 'admin',
          aigw_credentials_enc: Buffer.from('enc:test123').toString('base64'),
        },
      },
    });
    const { requestJson, requests } = makeRequestJson([
      { token: 'jwt-loaded', expiresAt: '2026-01-01T01:00:00.000Z' },
    ]);
    const service = makeService({ config, requestJson });

    await service.init();
    expect(requestJson).not.toHaveBeenCalled();

    await service.setServerUrl('http://127.0.0.1:8001');

    expect(await service.getJwt()).toBe('jwt-loaded');
    expect(JSON.parse(requests[0].init?.body ?? '{}')).toEqual({
      username: 'admin',
      password: 'test123',
      gateway_url: 'http://gateway',
    });
  });

  it('refreshes a JWT that is inside the expiry buffer', async () => {
    const config = makeConfig({ plugin_config: { 'aigw-base': {} } });
    const { requestJson } = makeRequestJson([
      { token: 'jwt-old', expiresAt: '2026-01-01T00:00:40.000Z' },
      { token: 'jwt-new', expiresAt: '2026-01-01T01:00:00.000Z' },
    ]);
    const service = makeService({
      config,
      requestJson,
      now: new Date('2026-01-01T00:00:15.000Z'),
    });

    await service.init();
    await service.setServerUrl('http://127.0.0.1:8001');
    const login = await service.login({ username: 'admin', password: 'test123' });

    expect(login.ok).toBe(true);
    expect(await service.getJwt()).toBe('jwt-new');
    expect(requestJson).toHaveBeenCalledTimes(2);
  });

  it('falls back to plaintext persistence with a warning when safeStorage is unavailable', async () => {
    const config = makeConfig({ plugin_config: { 'aigw-base': {} } });
    const { requestJson } = makeRequestJson([
      { token: 'jwt-plain', expiresAt: '2026-01-01T01:00:00.000Z' },
    ]);
    const service = makeService({ config, safeStorage: makeSafeStorage(false), requestJson });

    await service.init();
    await service.setServerUrl('http://127.0.0.1:8001');
    const result = await service.login({ username: 'admin', password: 'test123' });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.warning).toContain('plaintext');
      expect(result.snapshot.storedInPlaintext).toBe(true);
    }
    expect(aigwBase(config.current())).toMatchObject({
      aigw_credentials_username: 'admin',
      aigw_credentials_plaintext: 'test123',
      aigw_credentials_storage: 'plaintext',
    });
  });

  it('honors remember-me off by clearing persisted credentials while keeping the in-run JWT', async () => {
    const config = makeConfig({
      plugin_config: {
        'aigw-base': {
          aigw_credentials_username: 'old',
          aigw_credentials_plaintext: 'old-password',
        },
      },
    });
    const { requestJson } = makeRequestJson([
      { token: 'jwt-old', expiresAt: '2026-01-01T01:00:00.000Z' },
      { token: 'jwt-session', expiresAt: '2026-01-01T01:00:00.000Z' },
    ]);
    const service = makeService({ config, requestJson });

    await service.init();
    await service.setServerUrl('http://127.0.0.1:8001');
    const result = await service.login(
      { username: 'admin', password: 'test123' },
      { persist: false },
    );

    expect(result.ok).toBe(true);
    expect(await service.getJwt()).toBe('jwt-session');
    expect(aigwBase(config.current())).not.toHaveProperty('aigw_credentials_username');
    expect(aigwBase(config.current())).not.toHaveProperty('aigw_credentials_plaintext');
  });

  it('logs out through SF and clears in-memory and persisted credentials', async () => {
    const config = makeConfig({ plugin_config: { 'aigw-base': {} } });
    const { requestJson, requests } = makeRequestJson([
      { token: 'jwt-logout', expiresAt: '2026-01-01T01:00:00.000Z' },
    ]);
    const service = makeService({ config, requestJson });

    await service.init();
    await service.setServerUrl('http://127.0.0.1:8001');
    await service.login({ username: 'admin', password: 'test123' });
    const snapshot = await service.logout();

    expect(snapshot.isLoggedIn).toBe(false);
    expect(await service.getJwt()).toBeNull();
    expect(requests.at(-1)?.url).toBe('http://127.0.0.1:8001/aigateway/session/logout');
    expect(aigwBase(config.current())).not.toHaveProperty('aigw_credentials_username');
    expect(aigwBase(config.current())).not.toHaveProperty('aigw_credentials_enc');
  });

  it('persists validated gateway URLs under plugin_config.aigw-base', () => {
    const config = makeConfig({ plugin_config: { 'aigw-base': {} } });
    const service = makeService({ config });

    const snapshot = service.setGatewayUrl('https://gateway.example.com/aigw/?x=1#token');

    expect(snapshot.gatewayUrl).toBe('https://gateway.example.com/aigw');
    expect(aigwBase(config.current())).toMatchObject({
      mode: 'external',
      gateway_url: 'https://gateway.example.com/aigw',
    });
    expect(() => service.setGatewayUrl('https://user:pass@gateway.example.com')).toThrow(
      'must not include credentials',
    );
    expect(() => service.setGatewayUrl('http://gateway.example.com')).toThrow('must use HTTPS');
    expect(() => service.setGatewayUrl('http://127.evil.com')).toThrow('must use HTTPS');
  });

  it('allows insecure gateway URLs only for loopback hosts', () => {
    const config = makeConfig({ plugin_config: { 'aigw-base': {} } });
    const service = makeService({ config });

    expect(service.setGatewayUrl('http://localhost:9105').gatewayUrl).toBe('http://localhost:9105');
    expect(service.setGatewayUrl('http://127.0.0.1:9105').gatewayUrl).toBe('http://127.0.0.1:9105');
    expect(service.setGatewayUrl('http://[::1]:9105').gatewayUrl).toBe('http://[::1]:9105');
  });
});
