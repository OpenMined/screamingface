import { describe, expect, it } from 'vitest';

import {
  isAllowedExternalBrowserUrl,
  isAllowedOAuthAuthorizeUrl,
  isAllowedPopupUrl,
  isAllowedServerFetchUrl,
  isSafeBackendName,
  isSafeOAuthConnectionId,
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
          // Google policy pins exact client_ids; use the real Gemini id.
          client_id: '681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com',
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

  it('allows OAuth callbacks on the current external gateway port only when supplied', () => {
    const externalClaudeUrl = authorizeUrl('claude.com', '/cai/oauth/authorize', {
      response_type: 'code',
      client_id: 'public-client-id',
      redirect_uri: 'http://localhost:9106/callback',
      scope: 'read write',
      code_challenge: 'challenge',
      code_challenge_method: 'S256',
      state: 'state',
    });

    expect(isAllowedOAuthAuthorizeUrl(externalClaudeUrl)).toBe(false);
    expect(isAllowedOAuthAuthorizeUrl(externalClaudeUrl, { allowedRedirectPorts: ['9106'] })).toBe(
      true,
    );
  });

  it('rejects hosted HTTPS gateway OAuth callback URLs', () => {
    const hostedClaudeUrl = authorizeUrl('claude.com', '/cai/oauth/authorize', {
      response_type: 'code',
      client_id: 'public-client-id',
      redirect_uri: 'https://gateway.screamingface.ai/callback',
      scope: 'read write',
      code_challenge: 'challenge',
      code_challenge_method: 'S256',
      state: 'state',
    });

    expect(isAllowedOAuthAuthorizeUrl(hostedClaudeUrl)).toBe(false);
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
          // Real Gemini client_id so this case isolates the redirect-path rejection.
          client_id: '681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com',
          redirect_uri: 'http://localhost:9105/callback',
        }),
      ),
    ).toBe(false);
    expect(isAllowedOAuthAuthorizeUrl(authorizeUrl('auth.openai.com', '/login', base))).toBe(false);
  });

  it('pins exact Google OAuth client_ids on the loopback policy', () => {
    const googleBase = {
      response_type: 'code',
      redirect_uri: 'http://localhost:9105/oauth2callback',
      scope: 'https://www.googleapis.com/auth/cloud-platform',
      code_challenge: 'challenge',
      code_challenge_method: 'S256',
      state: 'state',
      access_type: 'offline',
      prompt: 'consent',
    };
    const GEMINI_CLIENT_ID =
      '681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com';
    const ANTIGRAVITY_CLIENT_ID =
      '1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com';

    // Both pinned Google client_ids are allowed.
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('accounts.google.com', '/o/oauth2/v2/auth', {
          ...googleBase,
          client_id: GEMINI_CLIENT_ID,
        }),
      ),
    ).toBe(true);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('accounts.google.com', '/o/oauth2/v2/auth', {
          ...googleBase,
          client_id: ANTIGRAVITY_CLIENT_ID,
        }),
      ),
    ).toBe(true);

    // Any other client_id on the Google policy is now BLOCKED (was allowed
    // when only presence was checked — U17 tightening).
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('accounts.google.com', '/o/oauth2/v2/auth', {
          ...googleBase,
          client_id: 'public-client-id',
        }),
      ),
    ).toBe(false);
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('accounts.google.com', '/o/oauth2/v2/auth', {
          ...googleBase,
          client_id: 'attacker-client-id.apps.googleusercontent.com',
        }),
      ),
    ).toBe(false);
  });

  it('accepts all loopback hosts in the OAuth redirect_uri', () => {
    const GEMINI_CLIENT_ID =
      '681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com';
    const base = {
      response_type: 'code',
      client_id: GEMINI_CLIENT_ID,
      scope: 'https://www.googleapis.com/auth/cloud-platform',
      code_challenge: 'challenge',
      code_challenge_method: 'S256',
      state: 'state',
    };
    // The SF callback bridge supports localhost / 127.0.0.1 / [::1]; the Desktop
    // policy must accept the same loopback hosts (review #7).
    for (const host of ['localhost', '127.0.0.1', '[::1]']) {
      expect(
        isAllowedOAuthAuthorizeUrl(
          authorizeUrl('accounts.google.com', '/o/oauth2/v2/auth', {
            ...base,
            redirect_uri: `http://${host}:9105/oauth2callback`,
          }),
        ),
      ).toBe(true);
    }
    // Non-loopback host is still rejected.
    expect(
      isAllowedOAuthAuthorizeUrl(
        authorizeUrl('accounts.google.com', '/o/oauth2/v2/auth', {
          ...base,
          redirect_uri: 'http://evil.example.com:9105/oauth2callback',
        }),
      ),
    ).toBe(false);
  });

  it('allows only safe backend path slugs', () => {
    expect(isSafeBackendName('browser-backend')).toBe(true);
    expect(isSafeBackendName('backend123')).toBe(true);

    expect(isSafeBackendName('../backend')).toBe(false);
    expect(isSafeBackendName('backend/profile')).toBe(false);
    expect(isSafeBackendName('Backend')).toBe(false);
  });

  it('allows only UUID-shaped OAuth connection IDs', () => {
    expect(isSafeOAuthConnectionId('00000000-0000-0000-0000-000000000001')).toBe(true);
    expect(isSafeOAuthConnectionId('A0000000-0000-0000-0000-000000000001')).toBe(true);

    expect(isSafeOAuthConnectionId('../auth/profiles/default')).toBe(false);
    expect(isSafeOAuthConnectionId('00000000-0000-0000-0000-000000000001/refresh')).toBe(false);
    expect(isSafeOAuthConnectionId('00000000-0000-0000-0000-000000000001?x=1')).toBe(false);
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
