// apps/desktop/src/main/services/publish-context.ts
//
// Resolves everything the renderer needs to publish an eval result to the public
// scoreboard but cannot read itself (env vars, app version, platform). The
// renderer hook (use-publish-score) builds and POSTs the payload; this only
// supplies context. Resolution order for URLs: env var → sf.json config → default.

import { app } from 'electron';
import { configService } from './config-service';

/**
 * Production scoreboard + portal are the defaults so packaged builds publish
 * (and link out) without any override; local dev points elsewhere via
 * SF_SCOREBOARD_URL / SF_PORTAL_URL or sf.json.
 */
const DEFAULT_SCOREBOARD_URL = 'https://scoreboard.screamingface.ai';
const DEFAULT_PORTAL_URL = 'https://screamingface.ai/portal/';

export interface PublishClientInfo {
  name: string;
  version: string;
  platform: string;
}

export interface PublishContext {
  scoreboardUrl: string;
  portalUrl: string;
  client: PublishClientInfo;
}

function configString(key: string): string | undefined {
  try {
    const value = configService.read()[key];
    return typeof value === 'string' && value.length > 0 ? value : undefined;
  } catch {
    // Config not readable (e.g. before init) — fall through to env/default.
    return undefined;
  }
}

function resolveUrl(envKey: string, configKey: string, fallback: string): string {
  const fromEnv = process.env[envKey];
  if (fromEnv && fromEnv.length > 0) return fromEnv;
  return configString(configKey) ?? fallback;
}

export function resolvePublishContext(): PublishContext {
  return {
    scoreboardUrl: resolveUrl('SF_SCOREBOARD_URL', 'scoreboard_url', DEFAULT_SCOREBOARD_URL),
    portalUrl: resolveUrl('SF_PORTAL_URL', 'portal_url', DEFAULT_PORTAL_URL),
    client: {
      name: 'screamingface-desktop',
      version: app.getVersion(),
      platform: process.platform,
    },
  };
}
