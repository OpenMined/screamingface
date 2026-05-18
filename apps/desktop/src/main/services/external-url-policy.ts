const BACKEND_NAME_RE = /^[a-z0-9-]+$/;
const OAUTH_CONNECTION_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const OAUTH_AUTHORIZE_POLICIES = new Map<
  string,
  { authorizePath: string; redirectPath: string; ports: Set<string> }
>([
  [
    'auth.openai.com',
    {
      authorizePath: '/oauth/authorize',
      redirectPath: '/auth/callback',
      ports: new Set(['1455', '1457']),
    },
  ],
  [
    'chatgpt.com',
    {
      authorizePath: '/oauth/authorize',
      redirectPath: '/auth/callback',
      ports: new Set(['1455', '1457']),
    },
  ],
  [
    'claude.com',
    { authorizePath: '/cai/oauth/authorize', redirectPath: '/callback', ports: new Set(['9105']) },
  ],
  [
    'claude.ai',
    { authorizePath: '/oauth/authorize', redirectPath: '/callback', ports: new Set(['9105']) },
  ],
  [
    'accounts.google.com',
    {
      authorizePath: '/o/oauth2/v2/auth',
      redirectPath: '/oauth2callback',
      ports: new Set(['9105']),
    },
  ],
]);

type LocalServerInfo = {
  scheme: string;
  host: string;
  port: number;
};

export function isSafeBackendName(backendName: string): boolean {
  return BACKEND_NAME_RE.test(backendName);
}

export function isSafeOAuthConnectionId(connectionId: string): boolean {
  return OAUTH_CONNECTION_ID_RE.test(connectionId);
}

export function isAllowedOAuthAuthorizeUrl(urlString: string): boolean {
  const url = parseHttpsUrl(urlString);
  if (!url) return false;
  const policy = OAUTH_AUTHORIZE_POLICIES.get(url.hostname);
  if (!policy) return false;
  if (url.pathname !== policy.authorizePath) return false;

  const params = url.searchParams;
  if (!hasSingleParam(params, 'response_type', 'code')) return false;
  if (!hasSingleParam(params, 'client_id')) return false;
  if (!hasSingleParam(params, 'redirect_uri')) return false;
  if (!hasSingleParam(params, 'scope')) return false;
  if (!hasSingleParam(params, 'state')) return false;
  if (!hasSingleParam(params, 'code_challenge')) return false;
  if (!hasSingleParam(params, 'code_challenge_method', 'S256')) return false;

  const redirectUri = params.get('redirect_uri');
  if (!redirectUri || !isLoopbackRedirectUri(redirectUri, policy)) {
    return false;
  }

  return true;
}

export function isAllowedExternalBrowserUrl(urlString: string): boolean {
  let url: URL;
  try {
    url = new URL(urlString);
  } catch {
    return false;
  }

  return url.protocol === 'https:' && url.username === '' && url.password === '';
}

export function isAllowedServerFetchUrl(
  urlString: string,
  serverInfo: LocalServerInfo | null,
): boolean {
  if (!serverInfo) return false;

  let url: URL;
  try {
    url = new URL(urlString);
  } catch {
    return false;
  }

  const expectedProtocol = `${serverInfo.scheme}:`;
  if (url.protocol !== expectedProtocol) return false;
  if (url.username || url.password) return false;
  if (!isLoopbackHostname(url.hostname)) return false;
  if (!isLoopbackOrWildcardHostname(serverInfo.host)) return false;
  return url.port === String(serverInfo.port);
}

export function isAllowedPopupUrl(urlString: string): boolean {
  let url: URL;
  try {
    url = new URL(urlString);
  } catch {
    return false;
  }

  return (
    url.protocol === 'http:' &&
    isLoopbackHostname(url.hostname) &&
    url.port === '6006' &&
    url.username === '' &&
    url.password === ''
  );
}

function parseHttpsUrl(urlString: string): URL | null {
  try {
    const url = new URL(urlString);
    if (url.protocol !== 'https:') return null;
    if (url.username || url.password || url.port) return null;
    return url;
  } catch {
    return null;
  }
}

function hasSingleParam(params: URLSearchParams, name: string, expectedValue?: string): boolean {
  const values = params.getAll(name);
  if (values.length !== 1 || values[0] === '') return false;
  return expectedValue === undefined || values[0] === expectedValue;
}

function isLoopbackRedirectUri(
  redirectUri: string,
  policy: { redirectPath: string; ports: Set<string> },
): boolean {
  try {
    const url = new URL(redirectUri);
    return (
      url.protocol === 'http:' &&
      url.hostname === 'localhost' &&
      policy.ports.has(url.port) &&
      url.pathname === policy.redirectPath &&
      url.search === '' &&
      url.hash === '' &&
      url.username === '' &&
      url.password === ''
    );
  } catch {
    return false;
  }
}

function isLoopbackHostname(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]';
}

function isLoopbackOrWildcardHostname(hostname: string): boolean {
  return isLoopbackHostname(hostname) || hostname === '0.0.0.0';
}
