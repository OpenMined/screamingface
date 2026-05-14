import { shell } from 'electron';

const ALLOWED_EXTERNAL_HOSTS = new Set([
  'claude.ai',
  'console.anthropic.com',
  'auth.openai.com',
  'chatgpt.com',
]);

export function isAllowedExternalUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' && ALLOWED_EXTERNAL_HOSTS.has(parsed.hostname);
  } catch {
    return false;
  }
}

export async function openAllowedExternalUrl(url: string): Promise<boolean> {
  if (!isAllowedExternalUrl(url)) return false;
  await shell.openExternal(url);
  return true;
}
