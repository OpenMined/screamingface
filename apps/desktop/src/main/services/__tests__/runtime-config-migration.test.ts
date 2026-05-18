import { join } from 'path';
import { describe, expect, it } from 'vitest';

import { migrateDesktopRuntimeConfig } from '../runtime-config-migration';

const USER_DATA = '/tmp/sf-user-data';

describe('migrateDesktopRuntimeConfig', () => {
  it('replaces active direct Codex backend with gateway-backed Codex', () => {
    const migrated = migrateDesktopRuntimeConfig(
      {
        version: '0.1.0',
        server: { host: '0.0.0.0', port: 8000, ssl: true },
        plugins: ['tracing', 'codex-backend-api', 'gemini-backend-api'],
        plugin_config: {
          'codex-backend-api': {
            default_model: 'o4-mini',
            timeout_seconds: 120,
          },
          'gemini-backend-api': { default_model: 'gemini-2.5-pro' },
        },
      },
      USER_DATA,
    );

    expect(migrated.plugins).toEqual([
      'tracing',
      'aigw-codex-backend',
      'gemini-backend-api',
      'aigw-runner',
      'aigw-base',
    ]);
    expect(migrated.server).toEqual({ host: '127.0.0.1', port: 8000, ssl: true });
    expect(migrated.plugin_config).toMatchObject({
      'aigw-codex-backend': {
        default_model: 'codex/gpt-5.4-mini',
        timeout_seconds: 120,
        gateway_url: 'http://127.0.0.1:9105',
        auth_profile: 'default',
      },
      'gemini-backend-api': { default_model: 'gemini-2.5-pro' },
    });
    expect(
      (migrated.plugin_config as Record<string, unknown>)['codex-backend-api'],
    ).toBeUndefined();
  });

  it('preserves an existing gateway Codex config when both backend names are present', () => {
    const migrated = migrateDesktopRuntimeConfig(
      {
        plugins: ['aigw-codex-backend', 'codex-backend-api'],
        plugin_config: {
          'aigw-codex-backend': {
            default_model: 'codex/gpt-5.5',
            auth_profile: 'work',
          },
          'codex-backend-api': {
            default_model: 'o4-mini',
            auth_profile: 'legacy',
          },
        },
      },
      USER_DATA,
    );

    expect(migrated.plugins).toEqual(['aigw-codex-backend', 'aigw-runner', 'aigw-base']);
    expect(migrated.plugin_config).toMatchObject({
      'aigw-codex-backend': {
        default_model: 'codex/gpt-5.5',
        auth_profile: 'work',
      },
    });
    expect(
      (migrated.plugin_config as Record<string, unknown>)['codex-backend-api'],
    ).toBeUndefined();
  });

  it('does not inject Codex when direct Codex was not active', () => {
    const migrated = migrateDesktopRuntimeConfig(
      {
        plugins: ['gemini-backend-api'],
        plugin_config: {
          'codex-backend-api': { default_model: 'o4-mini' },
          'gemini-backend-api': { default_model: 'gemini-2.5-pro' },
        },
      },
      USER_DATA,
    );

    expect(migrated.plugins).toEqual(['gemini-backend-api', 'aigw-runner', 'aigw-base']);
    expect(
      (migrated.plugin_config as Record<string, unknown>)['aigw-codex-backend'],
    ).toBeUndefined();
    expect(migrated.plugin_config).toMatchObject({
      'codex-backend-api': { default_model: 'o4-mini' },
    });
  });

  it('sets deterministic gateway runner defaults without lowering explicit timeout', () => {
    const migrated = migrateDesktopRuntimeConfig(
      {
        plugins: [],
        plugin_config: {
          'aigw-runner': {
            startup_timeout_seconds: 90,
            auth_enabled: true,
          },
        },
      },
      USER_DATA,
    );

    expect(migrated.plugin_config).toMatchObject({
      'aigw-runner': {
        aigateway_dir: join(USER_DATA, 'aigateway'),
        database_path: join(USER_DATA, 'aigateway', 'aigateway.db'),
        auth_enabled: false,
        startup_timeout_seconds: 90,
      },
    });
  });
});
