import { describe, expect, it } from 'vitest';

import {
  isAllowedExternalBrowserUrl,
  isAllowedOAuthAuthorizeUrl,
  isAllowedPopupUrl,
  isAllowedServerFetchUrl,
  isSafeBackendName,
} from '../external-url-policy';

function authorizeUrl(host: string, pathname: string, params: Record<string, string>): string {
  return `https://${host}${pathname}?${new URLSearchParams(params).toString()}`;
}

describe('external URL policy', () => {
  it('allows only safe HTTPS renderer external links', () => {
    expect(isAllowedExternalBrowserUrl('https://docs.example.test/project')).toBe(true);
    expect(isAllowedExternalBrowserUrl('https://source.example.test/org/project')).toBe(true);

    expect(isAllowedExternalBrowserUrl('file:///Users/example/.ssh/id_rsa')).toBe(false);
    expect(isAllowedExternalBrowserUrl('mailto:test@example.com')).toBe(false);
    expect(isAllowedExternalBrowserUrl('https://user:pass@example.test/project')).toBe(false);
  });

  it('allows OAuth authorize URLs with a gateway-owned loopback callback shape', () => {
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('auth.openai.com', '/oauth/authorize', {
          response_type: 'code',
          client_id: 'public-client-id',
          redirect_uri: 'http://localhost:1455/auth/callback',
          scope: 'read write',
          code_challenge: 'challenge',
          code_challenge_method: 'S256',
          state: 'state',
        }),
      ),
    ).toBe(true);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('chatgpt.com', '/oauth/authorize', {
          response_type: 'code',
          client_id: 'public-client-id',
          redirect_uri: 'http://localhost:1457/auth/callback',
          scope: 'read write',
          code_challenge: 'challenge',
          code_challenge_method: 'S256',
          state: 'state',
        }),
      ),
    ).toBe(true);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('claude.com', '/cai/oauth/authorize', {
          response_type: 'code',
          client_id: 'public-client-id',
          redirect_uri: 'http://localhost:9105/callback',
          scope: 'read write',
          code_challenge: 'challenge',
          code_challenge_method: 'S256',
          state: 'state',
        }),
      ),
    ).toBe(true);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('claude.ai', '/oauth/authorize', {
          response_type: 'code',
          client_id: 'public-client-id',
          redirect_uri: 'http://localhost:9105/callback',
          scope: 'read write',
          code_challenge: 'challenge',
          code_challenge_method: 'S256',
          state: 'state',
        }),
      ),
    ).toBe(true);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('accounts.google.com', '/o/oauth2/v2/auth', {
          response_type: 'code',
          client_id: 'public-client-id',
          redirect_uri: 'http://localhost:9105/oauth2callback',
          scope: 'https://www.googleapis.com/auth/cloud-platform',
          code_challenge: 'challenge',
          code_challenge_method: 'S256',
          state: 'state',
          access_type: 'offline',
          prompt: 'consent',
        }),
      ),
    ).toBe(true);
  });

  it('rejects malformed OAuth authorize URLs and non-loopback callbacks', () => {
    const base = {
      response_type: 'code',
      client_id: 'public-client-id',
      redirect_uri: 'http://localhost:9105/auth/callback',
      scope: 'read write',
      code_challenge: 'challenge',
      code_challenge_method: 'S256',
      state: 'state',
    };

    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('identity.example.test', '/oauth/authorize', {
          ...base,
        }),
      ),
    ).toBe(false);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('auth.openai.com', '/oauth/authorize', {
          ...base,
          redirect_uri: 'https://evil.test/auth/callback',
        }),
      ),
    ).toBe(false);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('auth.openai.com', '/oauth/authorize', {
          ...base,
          code_challenge_method: 'plain',
        }),
      ),
    ).toBe(false);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('auth.openai.com', '/oauth/authorize', {
          ...base,
          redirect_uri: 'http://localhost:22/auth/callback',
        }),
      ),
    ).toBe(false);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('auth.openai.com', '/oauth/authorize', {
          ...base,
          redirect_uri: 'http://localhost:1455/callback',
        }),
      ),
    ).toBe(false);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('accounts.google.com', '/o/oauth2/v2/auth', {
          ...base,
          redirect_uri: 'http://localhost:9105/callback',
        }),
      ),
    ).toBe(false);
    expect(isAllowedOAuthAuthorizeUrl(authorizeUrl('auth.openai.com', '/login', base))).toBe(false);
  });

  it('allows only safe backend path slugs', () => {
    expect(isSafeBackendName('browser-backend')).toBe(true);
    expect(isSafeBackendName('backend123')).toBe(true);

    expect(isSafeBackendName('../backend')).toBe(false);
    expect(isSafeBackendName('backend/profile')).toBe(false);
    expect(isSafeBackendName('Backend')).toBe(false);
  });

  it('allows server fetches only to the live loopback SF endpoint', () => {
    const serverInfo = { scheme: 'https', host: '127.0.0.1', port: 8000 };

    expect(isAllowedServerFetchUrl('https://127.0.0.1:8000/plugins', serverInfo)).toBe(true);
    expect(isAllowedServerFetchUrl('https://localhost:8000/plugins', serverInfo)).toBe(true);

    expect(isAllowedServerFetchUrl('https://127.0.0.1:8001/plugins', serverInfo)).toBe(false);
    expect(isAllowedServerFetchUrl('http://127.0.0.1:8000/plugins', serverInfo)).toBe(false);
    expect(isAllowedServerFetchUrl('https://192.168.1.5:8000/plugins', serverInfo)).toBe(false);
    expect(isAllowedServerFetchUrl('file:///tmp/x', serverInfo)).toBe(false);
  });

  it('allows popup windows only for local Phoenix tracing', () => {
    expect(isAllowedPopupUrl('http://localhost:6006')).toBe(true);
    expect(isAllowedPopupUrl('http://127.0.0.1:6006/projects')).toBe(true);

    expect(isAllowedPopupUrl('http://localhost:6007')).toBe(false);
    expect(isAllowedPopupUrl('https://localhost:6006')).toBe(false);
    expect(isAllowedPopupUrl('https://example.com')).toBe(false);
  });
});
